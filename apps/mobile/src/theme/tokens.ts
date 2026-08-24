/**
 * Tokens do design — a ÚNICA fonte de cor, tipografia e alvo de toque do app.
 *
 * Origem: `docs/design/artboards/17-style-guide.png`, transcrito em
 * `docs/design/README.md`. Espalhar hex por `StyleSheet` de componente garante
 * divergência no terceiro componente — e no React Native não há cascata de CSS
 * nem variável de tema herdada para consertar isso depois.
 *
 * O que este arquivo NÃO é: um sistema de temas. Não há provider, não há
 * contexto. `useCores()` lê o esquema do sistema e devolve a paleta certa —
 * quando isso não bastar (tema escolhido pelo usuário, artboard 12), aí sim
 * entra estado, e aí sim é decisão com gatilho.
 */

import { useColorScheme } from 'react-native';

/** Papéis de cor, nos dois esquemas. Nenhum componente conhece hex. */
export const cores = {
  light: {
    fundo: '#F7F5F2',
    superficie: '#FFFFFF',
    tinta: '#171614',
    secundario: '#6E6A62',
    acento: '#B44B31',
  },
  dark: {
    fundo: '#121211',
    superficie: '#1A1918',
    tinta: '#F2F0EC',
    // O style guide não define secundário no dark (a coluna está vazia no
    // artboard 17). Derivado da tinta com opacidade reduzida, e registrado
    // como divergência no card — não é valor do designer.
    secundario: '#8F8B83',
    acento: '#E4795C',
  },
} as const;

/**
 * Os PAPÉIS de cor, com o valor alargado para `string`.
 *
 * `as const` acima congela cada hex num tipo literal (`'#F7F5F2'`, não
 * `string`) — o que é ótimo para pegar erro de digitação e péssimo aqui: sem
 * este mapeamento, a paleta dark não é atribuível à light, porque `'#121211'`
 * não é `'#F7F5F2'`. O tipo garante que os dois esquemas tenham os MESMOS
 * papéis; os valores são livres.
 */
export type Cores = { readonly [P in keyof (typeof cores)['light']]: string };

/**
 * Escalas tipográficas do artboard 17. Os nomes são os PAPÉIS do design
 * ("correção", "apoio"), não tamanhos — `texto.correcao` sobrevive a uma
 * mudança de 19px para 20px; `texto.dezenove` não sobreviveria.
 *
 * `letterSpacing` no React Native é em PONTOS, não em `em` como no CSS. O
 * rótulo do design pede tracking .16em sobre 9.5px, o que dá 1.52pt.
 */
export const texto = {
  display: { fontSize: 30, fontWeight: '600', lineHeight: 36 },
  correcao: { fontSize: 19, fontWeight: '600', lineHeight: 25 },
  corpo: { fontSize: 16.5, fontWeight: '400', lineHeight: 24 },
  apoio: { fontSize: 13.5, fontWeight: '400', lineHeight: 20 },
  rotulo: { fontSize: 9.5, fontWeight: '600', letterSpacing: 1.52 },
} as const;

/** Alvos de toque. O mínimo do design é 48px; o botão de gravar, 84px. */
export const alvo = {
  minimo: 48,
  gravar: 84,
} as const;

/** Espaçamentos, em múltiplos de 4 — o que os artboards usam de fato. */
export const espaco = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 40,
} as const;

/** A paleta do esquema atual do sistema (`userInterfaceStyle: automatic`). */
export function useCores(): Cores {
  return useColorScheme() === 'dark' ? cores.dark : cores.light;
}
