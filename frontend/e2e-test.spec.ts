import { test, expect } from '@playwright/test';
import fs from 'node:fs';

const API_URL = 'http://127.0.0.1:8001';
const APP_URL = 'http://openclaw.deploymatrix.com/devsquad/';

test.describe('OpenClaw Multi-Agents - Backend', () => {
  
  test('backend health check', async ({ request }) => {
    const response = await request.get(`${API_URL}/health`);
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(data.ok).toBe(true);
    expect(data.service).toBe('dashboard_api');
    console.log('✅ Backend health OK');
  });

  test('API state endpoint', async ({ request }) => {
    const response = await request.get(`${API_URL}/api/state`);
    expect(response.ok()).toBeTruthy();
    const state = await response.json();
    console.log('State keys:', Object.keys(state));
    expect(state.agents).toBeDefined();
    expect(state.tasks).toBeDefined();
    console.log('✅ API state OK');
  });

  test('API models endpoint', async ({ request }) => {
    const response = await request.get(`${API_URL}/api/models`);
    expect(response.ok()).toBeTruthy();
    const models = await response.json();
    console.log('✅ API models OK');
  });

  test('API miniverse endpoint', async ({ request }) => {
    const response = await request.get(`${API_URL}/api/miniverse`);
    expect(response.ok()).toBeTruthy();
    const miniverse = await response.json();
    console.log('Miniverse source:', miniverse.meta?.source);
    console.log('Miniverse fallback:', miniverse.meta?.fallback);
    console.log('✅ API miniverse OK');
  });

  test('API gateway events', async ({ request }) => {
    const response = await request.get(`${API_URL}/api/gateway/events?limit=10`);
    expect(response.ok()).toBeTruthy();
    console.log('✅ API gateway events OK');
  });
});

test.describe('OpenClaw Multi-Agents - Frontend Build', () => {
  
  test('frontend dist exists', async () => {
    const distPath = '/var/www/openclaw-multi-agents/frontend/dist';
    expect(fs.existsSync(distPath)).toBe(true);
    expect(fs.existsSync(`${distPath}/index.html`)).toBe(true);
    expect(fs.existsSync(`${distPath}/assets`)).toBe(true);
    console.log('✅ Frontend dist exists');
  });

  test('frontend assets generated', async () => {
    const assetsPath = '/var/www/openclaw-multi-agents/frontend/dist/assets';
    const files = fs.readdirSync(assetsPath);
    const jsFiles = files.filter(f => f.endsWith('.js'));
    const cssFiles = files.filter(f => f.endsWith('.css'));
    
    expect(jsFiles.length).toBeGreaterThan(0);
    expect(cssFiles.length).toBeGreaterThan(0);
    console.log(`✅ Assets: ${jsFiles.length} JS, ${cssFiles.length} CSS`);
  });
});

test.describe('OpenClaw Multi-Agents - Browser Flow', () => {
  test('muestra la ejecución activa en el panel de ejecuciones', async ({ page }) => {
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });

    const runtimePanel = page.locator('.runtime-panel').first();
    await expect(runtimePanel.getByText('Ejecución activa')).toBeVisible({
      timeout: 15000,
    });
  });

  test('muestra reintento cuando la planificacion fallo', async ({ page }) => {
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('button', { name: 'Reintentar planificación' })).toBeVisible({
      timeout: 10000,
    });
  });

  test('guardar modelos persiste desde la vista de nuevo proyecto', async ({ page }) => {
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('heading', { name: 'Crear Nuevo Proyecto' })).toBeVisible();

    const archSelect = page.locator('.models-section select').first();
    await expect(archSelect).toBeVisible();

    const currentValue = await archSelect.inputValue();
    const preferredValue = 'blink/anthropic/claude-haiku-4.5';
    const fallbackValue = 'blink/openai/gpt-4.1';
    const nextValue = currentValue === preferredValue ? fallbackValue : preferredValue;

    await archSelect.selectOption(nextValue);

    const saveResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/devsquad/api/models') &&
        response.request().method() === 'PUT',
      { timeout: 10000 }
    );

    await page.getByRole('button', { name: /Guardar Modelos/ }).click();

    const saveResponse = await saveResponsePromise;
    expect(saveResponse.ok()).toBeTruthy();

    const payload = await saveResponse.json();
    expect(payload.saved).toBe(true);
    expect(payload.config.agents.arch.model).toBe(nextValue);

    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.locator('.models-section select').first()).toHaveValue(nextValue);
  });

  test('extiende el proyecto actual sin crear uno nuevo', async ({ page, request }) => {
    const beforeStateResponse = await request.get(`${API_URL}/api/state`);
    expect(beforeStateResponse.ok()).toBeTruthy();
    const beforeState: any = await beforeStateResponse.json();
    const currentProjectId = beforeState?.project?.id;
    expect(currentProjectId).toBeTruthy();
    const beforeTaskCount = Array.isArray(beforeState?.tasks) ? beforeState.tasks.length : 0;

    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.project-dropdown')).toBeVisible({ timeout: 10000 });
    await page.locator('.project-dropdown').selectOption(String(currentProjectId));
    const extensionPanel = page.locator('.tasks-list > .project-bar .project-extension');
    await expect(extensionPanel).toBeVisible({ timeout: 10000 });

    const extensionBrief = 'Agregar una verificación adicional de disponibilidad para el proyecto actual';
    await page.locator('.tasks-list > .project-bar .project-extension-textarea').fill(extensionBrief);

    const autoResumeCheckbox = page.locator('.tasks-list > .project-bar .project-extension-toggle input[type="checkbox"]');
    if (await autoResumeCheckbox.isChecked()) {
      await autoResumeCheckbox.uncheck();
    }

    const extendResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/devsquad/api/project/extend') &&
        response.request().method() === 'POST',
      { timeout: 10000 }
    );

    await page.locator('.tasks-list > .project-bar .project-extension button').click();

    const extendResponse = await extendResponsePromise;
    expect(extendResponse.ok()).toBeTruthy();
    const extendPayload: any = await extendResponse.json();
    expect(extendPayload.ok).toBe(true);
    expect(extendPayload.project_id).toBe(currentProjectId);
    expect(extendPayload.auto_resumed).toBe(false);
    expect(extendPayload.task_id).toMatch(/^T-/);

    const afterStateResponse = await request.get(`${API_URL}/api/state`);
    expect(afterStateResponse.ok()).toBeTruthy();
    const afterState: any = await afterStateResponse.json();
    expect(afterState?.project?.id).toBe(currentProjectId);
    expect(afterState?.project?.status).toBe('in_progress');
    expect(Array.isArray(afterState?.tasks)).toBe(true);
    expect(afterState.tasks.length).toBe(beforeTaskCount + 1);
    expect(
      afterState.tasks.some(
        (task: any) =>
          task.id === extendPayload.task_id &&
          String(task.description || '').includes(extensionBrief)
      )
    ).toBe(true);
    expect(
      Array.isArray(afterState?.project?.extensions) &&
        afterState.project.extensions.some((entry: any) => entry.task_id === extendPayload.task_id)
    ).toBe(true);
  });

  test('al cambiar de proyecto se recargan tareas, archivos y el preview de routes/tasks.js', async ({ page, request }) => {
    const stateResponse = await request.get(`${API_URL}/api/state`);
    expect(stateResponse.ok()).toBeTruthy();
    const state: any = await stateResponse.json();

    const visibleProjects = Array.isArray(state?.projects)
      ? state.projects.filter((project: any) => !['deleted', 'archived'].includes(project.status))
      : [];
    const primaryProject = visibleProjects.find((project: any) => project.id === state?.project?.id) || visibleProjects[0];
    const alternateProject = visibleProjects.find((project: any) => project.id !== primaryProject?.id);

    expect(primaryProject).toBeTruthy();
    expect(alternateProject).toBeTruthy();

    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    const dropdown = page.locator('.project-dropdown');
    await expect(dropdown).toBeVisible({ timeout: 10000 });

    await dropdown.selectOption(String(primaryProject.id));
    await expect(page.locator('.tasks-project-header h3')).toContainText(String(primaryProject.name), {
      timeout: 15000,
    });
    await page.locator('.tab-btn').filter({ hasText: 'Archivos' }).click();
    const filesTab = page.locator('.files-tab');
    await expect(filesTab.locator('.file-count')).toContainText('archivos', {
      timeout: 15000,
    });
    const primaryFileCountText = await filesTab.locator('.file-count').innerText();
    const routeTasksFile = filesTab.locator('.tree-item.file').filter({ hasText: 'tasks.js' }).nth(1);

    await expect(routeTasksFile).toBeVisible({ timeout: 15000 });
    await routeTasksFile.click();
    await expect(filesTab.locator('.file-preview')).toContainText('Archivo archivado', { timeout: 15000 });
    await expect(filesTab.locator('.file-preview')).toContainText('module.exports = router', {
      timeout: 15000,
    });

    await dropdown.selectOption(String(alternateProject.id));
    await expect(page.locator('.tasks-project-header h3')).toContainText(String(alternateProject.name), {
      timeout: 15000,
    });
    await expect(filesTab.locator('.file-preview')).toHaveCount(0);

    await page.locator('.tab-btn').filter({ hasText: 'Archivos' }).click();
    await expect(filesTab.locator('.file-count')).toContainText('archivos', {
      timeout: 15000,
    });
    const alternateFileCountText = await filesTab.locator('.file-count').innerText();
    expect(alternateFileCountText).not.toBe(primaryFileCountText);

    await dropdown.selectOption(String(primaryProject.id));
    await expect(page.locator('.tasks-project-header h3')).toContainText(String(primaryProject.name), {
      timeout: 15000,
    });
    await page.locator('.tab-btn').filter({ hasText: 'Archivos' }).click();
    await expect(filesTab.locator('.file-count')).toContainText('archivos', {
      timeout: 15000,
    });
    await expect(routeTasksFile).toBeVisible({
      timeout: 15000,
    });
    await routeTasksFile.click();
    await expect(filesTab.locator('.file-preview')).toContainText('module.exports = router', {
      timeout: 15000,
    });
  });
});
