import { createBrowserRouter } from 'react-router-dom';
import { ThreePanelLayout } from '@/pages/ThreePanelLayout';
import { Dashboard } from '@/pages/Dashboard';

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
], {
  basename: '/devsquad',
});