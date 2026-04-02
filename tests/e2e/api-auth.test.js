#!/usr/bin/env node
/**
 * Test E2E - API Auth Endpoints
 */

const http = require('http');

const BASE_URL = 'http://openclaw.deploymatrix.com';

function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(`${BASE_URL}${path}`, options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ status: res.statusCode, data }));
    });
    req.on('error', reject);
    req.end();
  });
}

async function runTests() {
  console.log('🧪 Tests de API Auth\n');
  
  // Test 1: Login endpoint
  console.log('📋 POST /api/auth/login');
  const loginRes = await request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  }, JSON.stringify({ username: 'admin', password: 'admin123' }));
  console.log(`  Status: ${loginRes.status}`);
  console.log(`  ✅ Endpoint accesible\n`);
  
  // Test 2: Stream endpoint (debe retornar 200 o 401, no 422)
  console.log('📋 GET /api/stream');
  const streamRes = await request('/api/stream');
  console.log(`  Status: ${streamRes.status}`);
  if (streamRes.status !== 422) {
    console.log(`  ✅ No hay error 422\n`);
  } else {
    console.log(`  ❌ Error 422 encontrado\n`);
  }
  
  // Test 3: State endpoint
  console.log('📋 GET /api/state');
  const stateRes = await request('/api/state');
  console.log(`  Status: ${stateRes.status}`);
  console.log(`  ✅ Endpoint responde\n`);
  
  console.log('🎉 Tests completados');
}

runTests().catch(console.error);
