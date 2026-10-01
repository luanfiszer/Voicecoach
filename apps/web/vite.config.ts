/**
 * Vite (ADR-0002). O ponto que não é óbvio é o `proxy`.
 *
 * **A web fala com a API na MESMA origem** (ADR-0077): o refresh mora num
 * cookie `SameSite=Strict` restrito a `/v1/auth/web`, e a API não tem CORS.
 * Em desenvolvimento quem garante a mesma origem é este proxy — o navegador
 * só conhece `localhost:5173`, e o Vite repassa `/v1` e `/health` para o
 * backend. Em produção, o mesmo papel é de um reverse proxy (CARD-055).
 */

import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

import pacote from './package.json' with { type: 'json' };

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VOICECOACH_');
  const backend = env.VOICECOACH_API_PROXY ?? 'http://localhost:8000';

  return {
    plugins: [react()],
    define: { __VERSAO_DA_WEB__: JSON.stringify(pacote.version) },
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        '/v1': { target: backend, changeOrigin: false },
        '/health': { target: backend, changeOrigin: false },
      },
    },
  };
});
