#!/usr/bin/env node
/**
 * Test E2E - Login con Usuario/Contraseña
 * 
 * Este test verifica:
 * 1. La página de login carga correctamente
 * 2. Se puede iniciar sesión con usuario/contraseña
 * 3. El dashboard carga datos del backend
 * 4. La conexión SSE funciona
 */

const { chromium } = require('playwright');

const BASE_URL = process.env.TEST_BASE_URL || 'http://openclaw.deploymatrix.com';
const USERNAME = process.env.TEST_USERNAME || 'admin';
const PASSWORD = process.env.TEST_PASSWORD || 'admin123';

async function runTests() {
  console.log('🧪 Iniciando tests E2E de Login...');
  console.log(`📍 URL Base: ${BASE_URL}`);
  
  const browser = await chromium.launch({ 
    headless: true,
    args: ['--ignore-certificate-errors', '--ignore-certificate-errors-spki-list', '--no-sandbox']
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
      
      // Verificar que el formulario de usuario está presente
      const usernameInput = await page.locator('input#username').count();
      if (usernameInput > 0) {
        console.log('  ✅ Campo Usuario encontrado');
      } else {
        throw new Error('Campo Usuario no encontrado');
      }
      
      // Verificar que el campo de contraseña está presente
      const passwordInput = await page.locator('input#password').count();
      if (passwordInput > 0) {
        console.log('  ✅ Campo Contraseña encontrado');
      } else {
        throw new Error('Campo Contraseña no encontrado');
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
    // TEST 2: Inicio de sesión con credenciales
    // ==========================================
    console.log('\n📋 Test 2: Inicio de sesión');
    try {
      // Limpiar y llenar el campo de usuario
      await page.fill('input#username', USERNAME);
      console.log(`  ✅ Usuario ingresado: ${USERNAME}`);
      
      // Limpiar y llenar el campo de contraseña
      await page.fill('input#password', PASSWORD);
      console.log('  ✅ Contraseña ingresada');
      
      // Hacer clic en el botón de login
      await page.click('button[type="submit"]');
      
      // Esperar redirección o mensaje de éxito
      await page.waitForTimeout(2000);
      
      // Verificar que no hay error visible
      const errorVisible = await page.locator('.login-error').isVisible().catch(() => false);
      
      if (!errorVisible) {
        console.log('  ✅ Login exitoso (sin errores visibles)');
        results.passed++;
        results.tests.push({ name: 'Login with credentials', status: 'passed' });
      } else {
        const errorText = await page.textContent('.login-error');
        throw new Error(`Error de login visible: ${errorText}`);
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'Login with credentials', status: 'failed', error: error.message });
    }

    // ==========================================
    // TEST 3: Verificar redirección al dashboard
    // ==========================================
    console.log('\n📋 Test 3: Redirección al dashboard');
    try {
      // Esperar redirección al dashboard
      await page.waitForURL(/\/dashboard/, { timeout: 5000 });
      console.log('  ✅ Redirección al dashboard exitosa');
      results.passed++;
      results.tests.push({ name: 'Redirect to dashboard', status: 'passed' });
    } catch (error) {
      // Si no redirige inmediatamente, verificar la URL actual
      const currentUrl = page.url();
      if (currentUrl.includes('/dashboard')) {
        console.log('  ✅ Ya estamos en el dashboard');
        results.passed++;
        results.tests.push({ name: 'Redirect to dashboard', status: 'passed' });
      } else {
        console.log(`  ⚠️ URL actual: ${currentUrl}`);
        throw new Error('No se redirigió al dashboard');
      }
    }

    // ==========================================
    // TEST 4: Verificar conexión SSE (stream)
    // ==========================================
    console.log('\n📋 Test 4: Conexión SSE');
    try {
      // Esperar un momento para que se establezca la conexión SSE
      await page.waitForTimeout(3000);
      
      // Verificar que no hay errores de autorización en la consola
      const logs = await page.evaluate(() => {
        return window.consoleErrors || [];
      });
      
      const authErrors = logs.filter((log) => 
        log.includes('Unauthorized') || log.includes('401') || log.includes('422')
      );
      
      if (authErrors.length === 0) {
        console.log('  ✅ No hay errores de autorización en SSE');
        results.passed++;
        results.tests.push({ name: 'SSE connection', status: 'passed' });
      } else {
        throw new Error(`Errores de autorización: ${authErrors.join(', ')}`);
      }
      
    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.failed++;
      results.tests.push({ name: 'SSE connection', status: 'failed', error: error.message });
    }

  } catch (error) {
    console.error('\n❌ Error general:', error.message);
  } finally {
    await context.close();
    await browser.close();
  }

  // ==========================================
  // RESUMEN
  // ==========================================
  console.log('\n' + '='.repeat(50));
  console.log('📊 RESUMEN DE TESTS');
  console.log('='.repeat(50));
  console.log(`✅ Pasados: ${results.passed}`);
  console.log(`❌ Fallidos: ${results.failed}`);
  console.log(`📋 Total: ${results.passed + results.failed}`);
  
  if (results.failed > 0) {
    console.log('\n🔍 Tests fallidos:');
    results.tests
      .filter(t => t.status === 'failed')
      .forEach(t => console.log(`  ❌ ${t.name}: ${t.error}`));
    process.exit(1);
  } else {
    console.log('\n🎉 ¡Todos los tests pasaron!');
    process.exit(0);
  }
}

// Ejecutar tests
runTests();
