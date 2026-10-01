import '@/theme/base.css';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';

import { App } from '@/App';
import { ProvedorDeSessao } from '@/features/auth/useSessao';

const raiz = document.getElementById('raiz');
if (raiz === null) throw new Error('index.html sem o elemento #raiz.');

createRoot(raiz).render(
  <StrictMode>
    <BrowserRouter>
      <ProvedorDeSessao>
        <App />
      </ProvedorDeSessao>
    </BrowserRouter>
  </StrictMode>,
);
