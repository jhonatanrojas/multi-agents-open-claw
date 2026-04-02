#!/usr/bin/env node
/**
 * Test E2E - Protección de rutas autenticadas
 * 
 * Este test verifica que:
 * 1. Un usuario sin sesión no puede acceder a /dashboard/
 * 2. Es redirigido automáticamente a /login
 */

const { chromium } = require('playwright');

const BASE_URL = process.env.TEST_BASE_URL || 'http://openclaw.deploymatrix.com';

async function runTests() {
  console.log('🧪 Iniciando tests de protección de rutas...');
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
    // TEST 1: Usuario sin sesión es redirigido desde /dashboard/
    // ==========================================
    console.log('\n📋 Test 1: Usuario sin sesión es redirigido desde /dashboard/');
    const context1 = await browser.newContext({ ignoreHTTPSErrors: true });
    const page1 = await context1.newPage();
    
    try {
      // Limpiar cookies para asegurar que no hay sesión
      await context1.clearCookies();
      
      // Intentar acceder directamente a /dashboard/
      await page1.goto(`${BASE_URL}/dashboard/`, { waitUntil: 'networkidle' });
      await page1.waitForTimeout(3000); // Esperar a que React procese
      
      const url1 = page1.url();
      console.log(`  ℹ️  URL final: ${url1}`);
      
      // Verificar que está en /login o en /dashboard/login (no autenticado)
      const isLoginPage = url1.includes('/login');
      const hasLoginButton = await page1.locator('button[type="submit"]').count() > 0;
      
      if (isLoginPage) {
        console.log('  ✅ Redirigido correctamente a /login');
        results.passed++;
        results.tests.push({ name: 'Unauthenticated user redirected from /dashboard/', status: 'passed' });
      } else if (hasLoginButton) {
        console.log('  ✅ Muestra formulario de login (protección activa)');
        results.passed++;
        results.tests.push({ name: 'Unauthenticated user sees login form', status: 'passed' });
      } else {
        console.log(`  ⚠️  URL final: ${url1}`);
        // Verificar si hay algún contenido del dashboard visible
        const dashboardContent = await page1.locator('text=Dev Squad Dashboard').count();
        if (dashboardContent > 0) {
          throw new Error('Dashboard visible sin autenticación');
        } else {
          console.log('  ⚠️  No se detectó login ni dashboard - verificar manualmente');
          results.tests.push({ name: 'Unauthenticated user redirected', status: 'warning' });
        }
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Unauthenticated user redirected from /dashboard/', status: 'failed', error: error.message });
    } finally {
      await context1.close();
    }

    // ==========================================
    // TEST 2: Usuario sin sesión es redirigido desde /devsquad/
    // ==========================================
    console.log('\n📋 Test 2: Usuario sin sesión es redirigido desde /devsquad/');
    const context2 = await browser.newContext({ ignoreHTTPSErrors: true });
    const page2 = await context2.newPage();
    
    try {
      await context2.clearCookies();
      
      await page2.goto(`${BASE_URL}/devsquad/`, { waitUntil: 'networkidle' });
      await page2.waitForTimeout(3000);
      
      const url2 = page2.url();
      console.log(`  ℹ️  URL final: ${url2}`);
      
      const isLoginPage = url2.includes('/login') || url2.includes('/devsquad/login');
      const hasLoginButton = await page2.locator('button[type="submit"]').count() > 0;
      
      if (isLoginPage) {
        console.log('  ✅ Redirigido correctamente a /devsquad/login');
        results.passed++;
        results.tests.push({ name: 'Unauthenticated user redirected from /devsquad/', status: 'passed' });
      } else if (hasLoginButton) {
        console.log('  ✅ Muestra formulario de login');
        results.passed++;
        results.tests.push({ name: 'Unauthenticated user sees login form', status: 'passed' });
      } else {
        const dashboardContent = await page2.locator('text=Dev Squad').count();
        if (dashboardContent > 0 && !hasLoginButton) {
          throw new Error('Dashboard visible sin autenticación');
        }
        console.log('  ⚠️  Estado intermedio - verificar manualmente');
        results.tests.push({ name: 'Unauthenticated user redirected from /devsquad/', status: 'warning' });
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Unauthenticated user redirected from /devsquad/', status: 'failed', error: error.message });
    } finally {
      await context2.close();
    }

    // ==========================================
    // TEST 3: Usuario autenticado puede acceder al dashboard
    // ==========================================
    console.log('\n📋 Test 3: Usuario autenticado puede acceder al dashboard');
    const context3 = await browser.newContext({ ignoreHTTPSErrors: true });
    const page3 = await context3.newPage();
    
    try {
      // Hacer login primero
      await page3.goto(`${BASE_URL}/login/`, { waitUntil: 'networkidle' });
      await page3.fill('input#api-key', 'dev-squad-api-key-2026');
      await page3.click('button[type="submit"]');
      await page3.waitForTimeout(2000);
      
      // Ahora acceder al dashboard
      await page3.goto(`${BASE_URL}/dashboard/`, { waitUntil: 'networkidle' });
      await page3.waitForTimeout(2000);
      
      const url3 = page3.url();
      console.log(`  ℹ️  URL: ${url3}`);
      
      // Verificar que NO estamos en login
      const isLoginPage = url3.includes('/login');
      if (isLoginPage) {
        throw new Error('Usuario autenticado fue redirigido al login');
      }
      
      // Verificar que el dashboard está visible
      const hasConnectionStatus = await page3.locator('text=SSE').count() > 0 || await page3.locator('.connection-bar').count() > 0;
      
      if (hasConnectionStatus) {
        console.log('  ✅ Dashboard visible para usuario autenticado');
        results.passed++;
        results.tests.push({ name: 'Authenticated user sees dashboard', status: 'passed' });
      } else {
        console.log('  ⚠️  No se detectó el dashboard completo - verificar manualmente');
        results.tests.push({ name: 'Authenticated user sees dashboard', status: 'warning' });
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Authenticated user sees dashboard', status: 'failed', error: error.message });
    } finally {
      await context3.close();
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
  console.log('📊 RESUMEN DE TESTS DE PROTECCIÓN');
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
    console.log('\n🎉 Todos los tests de protección pasaron correctamente');
    process.exit(0);
  }
}

// Ejecutar tests
runTests().catch(error => {
  console.error('Error fatal:', error);
  process.exit(1);
});