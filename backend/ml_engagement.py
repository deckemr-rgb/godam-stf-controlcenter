"""ML planner aman untuk engagement sosial.

Modul ini hanya menghasilkan rencana (dry-run). Tidak ada ADB, browser, STF,
atau API sosial yang dipanggil dari sini. Model menggunakan online logistic
ranking sederhana agar bobot dapat diperbarui dari feedback operator.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from dataclasses import dataclass
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
POSITIVE = {"bagus", "menarik", "inspiratif", "hebat", "penting", "baik", "keren", "bermanfaat"}
NEGATIVE = {"bohong", "benci", "buruk", "penipuan", "scam", "hoax", "marah", "ancaman"}
RISKY = {"klik link", "dm sekarang", "transfer", "crypto", "giveaway", "gratis", "jaminan untung"}
STOPWORDS = {"yang", "dan", "untuk", "dari", "dengan", "ini", "itu", "pada", "atau", "the", "and", "for"}


@dataclass
class AccountProfile:
    account_id: str
    topics: list[str]
    success_rate: float = 0.5
    daily_actions: int = 0
    daily_limit: int = 20
    cooldown_minutes: int = 60
    minutes_since_last_use: int = 1440
    logged_in: bool = True


class EngagementPlanner:
    """Pemberi skor tindakan dan pemilih akun tanpa mengeksekusi tindakan."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._weights = {
            "like": {"bias": -0.35, "relevance": 1.45, "sentiment": 0.35, "safety": 1.10, "fatigue": -1.20},
            "comment": {"bias": -0.70, "relevance": 1.60, "sentiment": 0.30, "safety": 1.55, "novelty": 0.85, "fatigue": -1.30},
            "share": {"bias": -1.10, "relevance": 1.20, "informative": 1.20, "safety": 1.75, "fatigue": -1.00},
        }
        self._pending: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [token.lower() for token in TOKEN_RE.findall(text) if token.lower() not in STOPWORDS]

    def features(
        self,
        caption: str,
        target_topics: list[str],
        recent_comments: list[str],
        daily_actions: int = 0,
        daily_limit: int = 20,
    ) -> dict[str, float]:
        lowered = caption.lower()
        tokens = self._tokens(caption)
        unique = set(tokens)
        topics = set(self._tokens(" ".join(target_topics)))
        overlap = len(unique & topics) / max(1, len(topics))
        positive = len(unique & POSITIVE)
        negative = len(unique & NEGATIVE)
        sentiment = max(0.0, min(1.0, 0.5 + (positive - negative) * 0.12))
        risk_hits = sum(term in lowered for term in RISKY)
        mention_risk = min(1.0, (caption.count("@") + caption.count("#")) / 12)
        safety = max(0.0, 1.0 - min(1.0, risk_hits * 0.35 + mention_risk * 0.45))
        informative = min(1.0, len(unique) / 35)
        novelty = 1.0 if not recent_comments else max(
            0.0,
            1.0 - max(self._jaccard(unique, set(self._tokens(item))) for item in recent_comments),
        )
        fatigue = min(1.0, daily_actions / max(1, daily_limit))
        return {
            "relevance": round(min(1.0, overlap), 4),
            "sentiment": round(sentiment, 4),
            "safety": round(safety, 4),
            "informative": round(informative, 4),
            "novelty": round(novelty, 4),
            "fatigue": round(fatigue, 4),
        }

    @staticmethod
    def _jaccard(left: set[str], right: set[str]) -> float:
        return len(left & right) / max(1, len(left | right))

    def probability(self, action: str, features: dict[str, float]) -> float:
        weights = self._weights[action]
        value = weights["bias"] + sum(
            weights.get(name, 0.0) * number for name, number in features.items()
        )
        return round(1.0 / (1.0 + math.exp(-value)), 4)

    def _comment_candidates(
        self,
        caption: str,
        tone: str,
        recent_comments: list[str],
    ) -> list[str]:
        topics = self._tokens(caption)
        subject = " ".join(topics[:3]) if topics else "topik ini"
        if tone == "netral":
            templates = [
                f"Informasinya tentang {subject} cukup jelas. Terima kasih sudah berbagi.",
                f"Pembahasan {subject} ini menarik untuk diikuti.",
                f"Sudut pandang tentang {subject} ini menambah referensi.",
            ]
        else:
            templates = [
                f"Pembahasan tentang {subject} sangat menarik. Terima kasih sudah berbagi!",
                f"Konten {subject} ini informatif dan mudah dipahami.",
                f"Menarik sekali melihat informasi tentang {subject} seperti ini.",
            ]
        recent = {re.sub(r"\s+", " ", item.strip().lower()) for item in recent_comments}
        return [item for item in templates if item.lower() not in recent]

    def rank_accounts(
        self,
        caption: str,
        accounts: list[AccountProfile],
    ) -> list[dict[str, Any]]:
        caption_tokens = set(self._tokens(caption))
        ranked = []
        for account in accounts:
            topic_tokens = set(self._tokens(" ".join(account.topics)))
            relevance = self._jaccard(caption_tokens, topic_tokens)
            cooldown_ready = min(1.0, account.minutes_since_last_use / max(1, account.cooldown_minutes))
            capacity = max(0.0, 1.0 - account.daily_actions / max(1, account.daily_limit))
            score = (
                relevance * 0.38
                + max(0.0, min(1.0, account.success_rate)) * 0.24
                + cooldown_ready * 0.18
                + capacity * 0.20
            )
            if not account.logged_in or capacity <= 0:
                score = 0.0
            ranked.append({
                "account_id": account.account_id,
                "score": round(score, 4),
                "eligible": bool(account.logged_in and capacity > 0 and cooldown_ready >= 1),
                "reasons": {
                    "topic_relevance": round(relevance, 4),
                    "success_rate": round(account.success_rate, 4),
                    "cooldown_ready": round(cooldown_ready, 4),
                    "capacity": round(capacity, 4),
                },
            })
        return sorted(ranked, key=lambda item: item["score"], reverse=True)

    def plan(
        self,
        *,
        platform: str,
        caption: str,
        tone: str,
        target_topics: list[str],
        recent_comments: list[str],
        accounts: list[AccountProfile],
        device_serials: list[str],
        current_accounts: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        ranked = self.rank_accounts(caption, accounts)
        eligible = [item for item in ranked if item["eligible"]]
        aggregate_actions = sum(account.daily_actions for account in accounts)
        aggregate_limit = sum(account.daily_limit for account in accounts) or 1
        features = self.features(
            caption,
            target_topics,
            recent_comments,
            aggregate_actions,
            aggregate_limit,
        )
        thresholds = {"like": 0.64, "comment": 0.70, "share": 0.76}
        decisions = []
        for action in ("like", "comment", "share"):
            confidence = self.probability(action, features)
            approved = bool(confidence >= thresholds[action] and features["safety"] >= 0.65)
            decisions.append({
                "action": action,
                "recommended": approved,
                "confidence": confidence,
                "threshold": thresholds[action],
                "execute": False,
                "reason": "Lolos model dan safety gate." if approved else "Belum melewati confidence/safety gate.",
            })

        assignments = []
        current_accounts = current_accounts or {}
        for index, serial in enumerate(device_serials):
            account_id = eligible[index % len(eligible)]["account_id"] if eligible else None
            assignments.append({
                "serial": serial,
                "current_account": current_accounts.get(serial),
                "recommended_account": account_id,
                "switch_required": bool(account_id and current_accounts.get(serial) != account_id),
                "execute": False,
            })

        comments = self._comment_candidates(caption, tone, recent_comments)
        material = f"{platform}|{caption}|{','.join(device_serials)}|{','.join(a.account_id for a in accounts)}"
        plan_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
        with self._lock:
            self._pending[plan_id] = {"features": features, "decisions": decisions}
        return {
            "plan_id": plan_id,
            "mode": "dry-run",
            "execute": False,
            "model_info": {
                "kind": "heuristic_with_in_memory_feedback",
                "calibrated": False,
                "note": "Skor eksperimen, bukan probabilitas keberhasilan. Tidak dilatih pada dataset tervalidasi; feedback hilang saat restart.",
                "accounts_verified": False,
            },
            "platform": platform,
            "features": features,
            "decisions": decisions,
            "comment_suggestions": comments[:3],
            "account_ranking": ranked,
            "device_assignments": assignments,
            "safety_gate": {
                "passed": features["safety"] >= 0.65,
                "mass_engagement_disabled": True,
            },
        }

    def learn(self, plan_id: str, action: str, accepted: bool, learning_rate: float = 0.05) -> dict[str, Any]:
        if action not in self._weights:
            raise ValueError("Action tidak didukung.")
        pending = self._pending.get(plan_id)
        if not pending:
            raise KeyError("Plan tidak ditemukan.")
        features = pending["features"]
        prediction = self.probability(action, features)
        error = (1.0 if accepted else 0.0) - prediction
        with self._lock:
            self._weights[action]["bias"] += learning_rate * error
            for name, value in features.items():
                if name in self._weights[action]:
                    self._weights[action][name] += learning_rate * error * value
        return {"action": action, "previous_probability": prediction, "accepted": accepted, "updated": True}


planner = EngagementPlanner()
