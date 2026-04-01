#!/usr/bin/env node
/**
 * Test E2E - Login y redirección en múltiples rutas
 * 
 * Este test verifica:
 * 1. /login - Redirige al dashboard correcto después del login
 * 2. /devsquad/login - Redirige a /devsquad/
 * 3. /dashboard/login - Redirige a /dashboard/
 * 4. La sesión persiste en cada ruta
 */

const { chromium } = require('playwright');

const BASE_URL = process.env.TEST_BASE_URL || 'http://openclaw.deploymatrix.com';
const API_KEY = process.env.TEST_API_KEY || 'dev-squad-api-key-2026';

async function runTests() {
  console.log('🧪 Iniciando tests E2E de rutas...');
  console.log(`📍 URL Base: ${BASE_URL}`);
  
  const browser = await chromium.launch({ 
    headless: true,
    args: ['--ignore-certificate-errors']
  });
  
  const results = {
    passed: 0,
    failed: 0,
    tests: []
  };

  try {
    // ==========================================
    // TEST 1: Login desde /login redirige a /
    // ==========================================
    console.log('\n📋 Test 1: Login desde /login');
    const context1 = await browser.newContext({ ignoreHTTPSErrors: true });
    const page1 = await context1.newPage();
    
    try {
      await page1.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' });
      await page1.fill('input#api-key', API_KEY);
      await page1.click('button[type="submit"]');
      await page1.waitForTimeout(2000);
      
      const url1 = page1.url();
      console.log(`  ℹ️  URL después del login: ${url1}`);
      
      // Verificar que no estamos en /login
      if (!url1.includes('/login')) {
        console.log('  ✅ Redirección exitosa desde /login');
        results.passed++;
        results.tests.push({ name: 'Login from /login redirects', status: 'passed', url: url1 });
      } else {
        throw new Error(`No se redirigió desde /login. URL: ${url1}`);
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Login from /login redirects', status: 'failed', error: error.message });
    } finally {
      await context1.close();
    }

    // ==========================================
    // TEST 2: Login desde /devsquad/login redirige a /devsquad/
    // ==========================================
    console.log('\n📋 Test 2: Login desde /devsquad/login');
    const context2 = await browser.newContext({ ignoreHTTPSErrors: true });
    const page2 = await context2.newPage();
    
    try {
      await page2.goto(`${BASE_URL}/devsquad/login`, { waitUntil: 'networkidle' });
      
      // Verificar que la página cargó
      const title = await page2.textContent('h1');
      if (!title.includes('Dev Squad')) {
        throw new Error(`Página no cargó correctamente. Título: ${title}`);
      }
      console.log('  ✅ Página /devsquad/login cargó correctamente');
      
      await page2.fill('input#api-key', API_KEY);
      await page2.click('button[type="submit"]');
      await page2.waitForTimeout(2000);
      
      const url2 = page2.url();
      console.log(`  ℹ️  URL después del login: ${url2}`);
      
      if (url2.includes('/devsquad/') && !url2.includes('login')) {
        console.log('  ✅ Redirección correcta a /devsquad/');
        results.passed++;
        results.tests.push({ name: 'Login from /devsquad/login redirects to /devsquad/', status: 'passed', url: url2 });
      } else {
        throw new Error(`Redirección incorrecta. Esperado: /devsquad/, Actual: ${url2}`);
      }
      
      // Verificar que el dashboard cargó
      const dashboardContent = await page2.locator('text=Dev Squad Dashboard,').count();
      if (dashboardContent > 0 || await page2.locator('.dashboard, [class*="dashboard"]').count() > 0) {
        console.log('  ✅ Dashboard cargó dentro de /devsquad/');
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Login from /devsquad/login redirects to /devsquad/', status: 'failed', error: error.message });
    } finally {
      await context2.close();
    }

    // ==========================================
    // TEST 3: Acceso directo a /devsquad/ muestra dashboard
    // ==========================================
    console.log('\n📋 Test 3: Acceso directo a /devsquad/');
    const context3 = await browser.newContext({ ignoreHTTPSErrors: true });
    const page3 = await context3.newPage();
    
    try {
      // Primero hacer login
      await page3.goto(`${BASE_URL}/devsquad/login`, { waitUntil: 'networkidle' });
      await page3.fill('input#api-key', API_KEY);
      await page3.click('button[type="submit"]');
      await page3.waitForTimeout(2000);
      
      // Ahora acceder directamente a /devsquad/
      await page3.goto(`${BASE_URL}/devsquad/`, { waitUntil: 'networkidle' });
      
      const url3 = page3.url();
      console.log(`  ℹ️  URL actual: ${url3}`);
      
      // Verificar que no redirigió a /login
      const sessionCheck = await page3.evaluate(async () => {
        try {
          const resp = await fetch('/api/auth/session', { credentials: 'include' });
          return await resp.json();
        } catch (e) {
          return { error: e.message };
        }
      });
      
      if (sessionCheck.authenticated) {
        console.log('  ✅ Sesión activa en /devsquad/');
        console.log(`  ℹ️  Usuario: ${sessionCheck.session?.user || 'N/A'}`);
        results.passed++;
        results.tests.push({ name: 'Direct access to /devsquad/ works', status: 'passed' });
      } else {
        throw new Error(`Sesión no autenticada: ${JSON.stringify(sessionCheck)}`);
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Direct access to /devsquad/ works', status: 'failed', error: error.message });
    } finally {
      await context3.close();
    }

    // ==========================================
    // TEST 4: Logout funciona en todas las rutas
    // ==========================================
    console.log('\n📋 Test 4: Logout desde /devsquad/');
    const context4 = await browser.newContext({ ignoreHTTPSErrors: true });
    const page4 = await context4.newPage();
    
    try {
      // Login primero
      await page4.goto(`${BASE_URL}/devsquad/login`, { waitUntil: 'networkidle' });
      await page4.fill('input#api-key', API_KEY);
      await page4.click('button[type="submit"]');
      await page4.waitForTimeout(2000);
      
      // Logout
      const logoutResult = await page4.evaluate(async () => {
        try {
          const resp = await fetch('/api/auth/logout', { 
            method: 'POST',
            credentials: 'include' 
          });
          return { status: resp.status, ok: resp.ok };
        } catch (e) {
          return { error: e.message };
        }
      });
      
      if (logoutResult.ok) {
        console.log('  ✅ Logout exitoso desde /devsquad/');
        
        // Verificar que la sesión se cerró
        const sessionCheck = await page4.evaluate(async () => {
          try {
            const resp = await fetch('/api/auth/session', { credentials: 'include' });
            return await resp.json();
          } catch (e) {
            return { error: e.message };
          }
        });
        
        if (!sessionCheck.authenticated) {
          console.log('  ✅ Sesión cerrada correctamente');
          results.passed++;
          results.tests.push({ name: 'Logout from /devsquad/ works', status: 'passed' });
        } else {
          throw new Error('Sesión sigue activa después del logout');
        }
      } else {
        throw new Error(`Logout falló: ${JSON.stringify(logoutResult)}`);
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Logout from /devsquad/ works', status: 'failed', error: error.message });
    } finally {
      await context4.close();
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
  console.log('📊 RESUMEN DE TESTS DE RUTAS');
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
    console.log('\n🎉 Todos los tests de rutas pasaron correctamente');
    process.exit(0);
  }
}

// Ejecutar tests
runTests().catch(error => {
  console.error('Error fatal:', error);
  process.exit(1);
});
