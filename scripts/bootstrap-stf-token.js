'use strict'

const crypto = require('crypto')
const r = require('/app/node_modules/rethinkdb')
const jwtutil = require('/app/lib/util/jwtutil.js').default

const email = process.env.STF_ADMIN_EMAIL || 'admin@localhost'
const name = process.env.STF_ADMIN_NAME || 'Godam Local Administrator'
const secret = process.env.SECRET
const title = 'godam-localhost-integration'

if (!secret) {
  throw new Error('SECRET tidak tersedia di container STF')
}

async function main() {
  const connection = await r.connect({host: 'stf-rethinkdb', port: 28015, db: 'stf'})
  const id = crypto.randomBytes(32).toString('hex')
  const jwt = jwtutil.encode({payload: {email, name}, secret})

  try {
    await r.table('accessTokens')
      .getAll(email, {index: 'email'})
      .filter({title})
      .delete()
      .run(connection)
    await r.table('accessTokens').insert({email, id, title, jwt}).run(connection)
    process.stdout.write(id)
  } finally {
    await connection.close()
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`)
  process.exit(1)
})
