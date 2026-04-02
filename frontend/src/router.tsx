import { createBrowserRouter } from 'react-router-dom';
import { ThreePanelLayout } from '@/pages/ThreePanelLayout';
import { Dashboard } from '@/pages/Dashboard';
import { LoginPage } from '@/pages/LoginPage';

// Detectar el base path actual (/ o /devsquad/)
const getBasePath = () => {
  const path = window.location.pathname;
  if (path.startsWith('/devsquad')) {
    return '/devsquad';
  }
  if (path.startsWith('/login')) {
    return '/';
  }
  if (path.startsWith('/dashboard')) {
    return '/dashboard';
  }
  return '/';
};

const basePath = getBasePath();

// Redirección después del login - va al dashboard correspondiente
const handleLoginSuccess = () => {
  if (basePath === '/devsquad') {
    window.location.href = '/devsquad/';
  } else {
    // Siempre ir a /dashboard/ después del login (no a / que redirige a login)
    window.location.href = '/dashboard/';
  }
};

export const router = createBrowserRouter([
  {
    path: '/',
    element: <ThreePanelLayout />,
    children: [
      {
        index: true,
        element: <Dashboard />,
      },
      {
        path: 'dashboard',
        element: <Dashboard />,
      },
    ],
  },
  {
    path: '/login',
    element: <LoginPage onLoginSuccess={handleLoginSuccess} />,
  },
  // Legacy routes for /devsquad
  {
    path: '/devsquad',
    element: <ThreePanelLayout />,
    children: [
      {
        index: true,
        element: <Dashboard />,
      },
      {
        path: 'dashboard',
        element: <Dashboard />,
      },
    ],
  },
  {
    path: '/devsquad/login',
    element: <LoginPage onLoginSuccess={() => window.location.href = '/devsquad/'} />,
  },
], {
  basename: '/',
});
