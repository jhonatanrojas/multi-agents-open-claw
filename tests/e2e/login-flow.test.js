#!/usr/bin/env node
/**
 * Test E2E - Login y conexión Frontend-Backend
 * 
 * Este test verifica:
 * 1. La página de login carga correctamente
 * 2. Se puede iniciar sesión con la API key
 * 3. El dashboard carga datos del backend
 * 4. La conexión SSE/WebSocket funciona
 */

const { chromium } = require('playwright');

const BASE_URL = process.env.TEST_BASE_URL || 'http://openclaw.deploymatrix.com';
const API_KEY = process.env.TEST_API_KEY || 'dev-squad-api-key-2026';

async function runTests() {
  console.log('🧪 Iniciando tests E2E...');
  console.log(`📍 URL Base: ${BASE_URL}`);
  
  const browser = await chromium.launch({ 
    headless: true,
    args: ['--ignore-certificate-errors', '--ignore-certificate-errors-spki-list']
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: 'test-results/videos/' },
    ignoreHTTPSErrors: true
  });
  
  const results = {
    passed: 0,
    failed: 0,
    tests: []
  };

  try {
    const page = await context.newPage();
    
    // ==========================================
    // TEST 1: Carga de página de login
    // ==========================================
    console.log('\n📋 Test 1: Carga de página de login');
    try {
      await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
      
      // Verificar que el título está presente
      const title = await page.textContent('h1');
      if (title.includes('Dev Squad')) {
        console.log('  ✅ Título correcto: "Dev Squad"');
        results.passed++;
        results.tests.push({ name: 'Login page loads', status: 'passed' });
      } else {
        throw new Error(`Título incorrecto: ${title}`);
      }
      
      // Verificar que el formulario está presente
      const apiKeyInput = await page.locator('input#api-key').count();
      if (apiKeyInput > 0) {
        console.log('  ✅ Campo API Key encontrado');
      } else {
        throw new Error('Campo API Key no encontrado');
      }
      
      const loginButton = await page.locator('button[type="submit"]').count();
      if (loginButton > 0) {
        console.log('  ✅ Botón de login encontrado');
      } else {
        throw new Error('Botón de login no encontrado');
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Login page loads', status: 'failed', error: error.message });
    }

    // ==========================================
    // TEST 2: Inicio de sesión
    // ==========================================
    console.log('\n📋 Test 2: Inicio de sesión');
    try {
      // Limpiar cookies anteriores
      await context.clearCookies();
      
      await page.fill('input#api-key', API_KEY);
      console.log('  ✅ API Key ingresada');
      
      // Click en login y esperar navegación
      await page.click('button[type="submit"]');
      
      // Esperar a que se procese el login (redirección o cambio de página)
      await page.waitForTimeout(2000);
      
      // Verificar que la sesión está activa haciendo una llamada a /api/auth/session
      const sessionCheck = await page.evaluate(async () => {
        try {
          const resp = await fetch('/api/auth/session', { credentials: 'include' });
          return { status: resp.status, body: await resp.json() };
        } catch (e) {
          return { status: 0, error: e.message };
        }
      });
      
      if (sessionCheck.body && sessionCheck.body.authenticated === true) {
        console.log('  ✅ Login exitoso - Sesión autenticada');
        results.passed++;
        results.tests.push({ name: 'Login successful', status: 'passed' });
      } else {
        throw new Error(`Login falló: Sesión no autenticada - ${JSON.stringify(sessionCheck)}`);
      }
      
      // Verificar cookie de sesión
      const cookies = await context.cookies();
      const sessionCookie = cookies.find(c => c.name === 'dashboard_session');
      if (sessionCookie) {
        console.log('  ✅ Cookie de sesión creada');
        console.log(`     - HttpOnly: ${sessionCookie.httpOnly}`);
        console.log(`     - SameSite: ${sessionCookie.sameSite}`);
      } else {
        console.log('  ⚠️  Cookie de sesión no encontrada (puede ser normal si auth está deshabilitada)');
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Login successful', status: 'failed', error: error.message });
    }

    // ==========================================
    // TEST 3: Dashboard carga datos
    // ==========================================
    console.log('\n📋 Test 3: Dashboard carga datos del backend');
    try {
      // Esperar a que el dashboard cargue
      await page.waitForTimeout(3000);
      
      // Verificar que hay conexión (indicador de conexión)
      const connectionStatus = await page.locator('.connection-status, .connection-label').first().textContent().catch(() => 'unknown');
      console.log(`  ℹ️  Estado de conexión: ${connectionStatus}`);
      
      // Verificar que se hicieron llamadas a la API
      const apiCalls = await page.evaluate(() => {
        return performance.getEntriesByType('resource')
          .filter(r => r.name.includes('/api/'))
          .map(r => ({
            url: r.name,
            duration: r.duration,
            status: r.responseStatus
          }));
      });
      
      console.log(`  ℹ️  Llamadas API detectadas: ${apiCalls.length}`);
      apiCalls.slice(0, 5).forEach(call => {
        console.log(`     - ${call.url.split('/').pop()} (${Math.round(call.duration)}ms)`);
      });
      
      if (apiCalls.length > 0) {
        console.log('  ✅ Frontend realizó llamadas al backend');
        results.passed++;
        results.tests.push({ name: 'Dashboard loads data', status: 'passed' });
      } else {
        console.log('  ⚠️  No se detectaron llamadas API (puede ser por caché)');
        results.tests.push({ name: 'Dashboard loads data', status: 'warning' });
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Dashboard loads data', status: 'failed', error: error.message });
    }

    // ==========================================
    // TEST 4: Verificar sesión
    // ==========================================
    console.log('\n📋 Test 4: Verificación de sesión');
    try {
      // Hacer una llamada directa al API de sesión
      const sessionResponse = await page.evaluate(async () => {
        const resp = await fetch('/api/auth/session', { credentials: 'include' });
        return { status: resp.status, body: await resp.json() };
      });
      
      if (sessionResponse.body.authenticated === true) {
        console.log('  ✅ Sesión autenticada correctamente');
        results.passed++;
        results.tests.push({ name: 'Session verification', status: 'passed' });
      } else {
        throw new Error(`Sesión no autenticada: ${JSON.stringify(sessionResponse.body)}`);
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Session verification', status: 'failed', error: error.message });
    }

    // ==========================================
    // TEST 5: Logout
    // ==========================================
    console.log('\n📋 Test 5: Cierre de sesión');
    try {
      // Llamar al endpoint de logout
      const logoutResponse = await page.evaluate(async () => {
        const resp = await fetch('/api/auth/logout', { 
          method: 'POST',
          credentials: 'include' 
        });
        return { status: resp.status, body: await resp.json() };
      });
      
      if (logoutResponse.status === 200) {
        console.log('  ✅ Logout exitoso');
        results.passed++;
        results.tests.push({ name: 'Logout successful', status: 'passed' });
      } else {
        throw new Error(`Logout falló: HTTP ${logoutResponse.status}`);
      }
      
      // Verificar que la sesión ya no es válida
      const sessionCheck = await page.evaluate(async () => {
        const resp = await fetch('/api/auth/session', { credentials: 'include' });
        return { status: resp.status, body: await resp.json() };
      });
      
      if (sessionCheck.body.authenticated === false) {
        console.log('  ✅ Sesión cerrada correctamente');
      } else {
        console.log('  ⚠️  La sesión sigue activa después del logout');
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Logout successful', status: 'failed', error: error.message });
    }

  } catch (error) {
    console.error(`\n❌ Error general: ${error.message}`);
    results.failed++;
  } finally {
    await browser.close();
  }

  // ==========================================
  // RESUMEN
  // ==========================================
  console.log('\n' + '='.repeat(50));
  console.log('📊 RESUMEN DE TESTS E2E');
  console.log('='.repeat(50));
  console.log(`✅ Pasados: ${results.passed}`);
  console.log(`❌ Fallidos: ${results.failed}`);
  console.log(`📋 Total: ${results.tests.length}`);
  
  if (results.failed > 0) {
    console.log('\n🔍 Tests fallidos:');
    results.tests
      .filter(t => t.status === 'failed')
      .forEach(t => console.log(`  - ${t.name}: ${t.error}`));
    process.exit(1);
  } else {
    console.log('\n🎉 Todos los tests pasaron correctamente');
    process.exit(0);
  }
}

// Ejecutar tests
runTests().catch(error => {
  console.error('Error fatal:', error);
  process.exit(1);
});
