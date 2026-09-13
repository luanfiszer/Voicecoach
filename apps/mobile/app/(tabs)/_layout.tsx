/**
 * A barra de abas do artboard 10 — `Falar · Histórico · Perfil` (CARD-029) —
 * mais `Configurações` (CARD-059, sem artboard: preferência de aparelho, não
 * de conta, e por isso não depende da autenticação que Perfil espera).
 *
 * **O grupo `(tabs)` é o que separa navegação de produto de rota de
 * ferramenta.** `medicao` e `diagnostico-silencio` ficam FORA deste diretório,
 * como irmãos de `(tabs)` dentro de `app/` — o parêntese tira o segmento da
 * URL (a rota continua `/`, `/historico`, `/perfil`) sem tirá-lo da árvore de
 * telas do produto. Colocar as duas rotas de medição aqui dentro as
 * transformaria em abas visíveis, que não são.
 *
 * `headerShown: false` pela mesma razão do `Stack` raiz: cada tela desenha o
 * próprio cabeçalho.
 */

import { Tabs } from 'expo-router';

import { alvo, useCores } from '@/theme/tokens';

export default function LayoutDeAbas() {
  const cores = useCores();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: cores.acento,
        tabBarInactiveTintColor: cores.secundario,
        tabBarStyle: { backgroundColor: cores.fundo, minHeight: alvo.minimo },
        // O artboard 10 mostra um círculo vazio sobre cada rótulo — placeholder
        // de design, não um glifo específico (nenhum ícone de casa/relógio/
        // pessoa foi desenhado). Sem biblioteca de ícones no projeto ainda
        // (nenhuma dependência nova sem ADR, critério 1 de `docs/adr/README.md`),
        // a escolha honesta é NENHUM ícone — não o triângulo de fallback do
        // React Navigation, que pareceria um ícone quebrado.
        tabBarIcon: () => null,
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Falar' }} />
      <Tabs.Screen name="historico" options={{ title: 'Histórico' }} />
      <Tabs.Screen name="perfil" options={{ title: 'Perfil' }} />
      <Tabs.Screen name="configuracoes" options={{ title: 'Configurações' }} />
    </Tabs>
  );
}
