import { test, expect } from '@playwright/test';
import fs from 'node:fs';

const API_URL = 'http://127.0.0.1:8001';

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
