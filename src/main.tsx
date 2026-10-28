import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from '@/app/App';
import '@/styles/globals.css';

async function bootstrap() {
  // MSW answers all requests when mocks are enabled (dev and tests only).
  if (import.meta.env.VITE_USE_MOCKS === 'true') {
    try {
      const { startMocks } = await import('@/mocks/browser');
      await startMocks();
    } catch (err) {
      console.error('Failed to start the mock API', err);
    }
  }

  const container = document.getElementById('root');
  if (!container) throw new Error('Root element #root is missing');

  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void bootstrap();
