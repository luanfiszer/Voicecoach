/**
 * Vitest — o runner de teste do cliente (ADR-0061).
 *
 * Deliberadamente mínimo: `environment: 'node'` (não `jsdom`), nenhum setup
 * file, nenhum mock de módulo nativo. O que se testa aqui é **lógica extraída
 * de componente**; o que depende de plataforma continua sendo verificado no
 * aparelho, e o ADR diz isso por escrito.
 */

import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['apps/*/src/**/*.test.ts', 'packages/*/src/**/*.test.ts'],
  },
});
