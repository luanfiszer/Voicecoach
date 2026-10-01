/**
 * A casca das telas logadas: marca + navegação + conteúdo da rota.
 *
 * As quatro abas do mobile (Conversa, Histórico, Perfil, Configurações)
 * viram links de topo — na web não há tab bar de polegar, há uma barra que o
 * mouse e o teclado alcançam. `NavLink` marca a aba da URL atual sozinho.
 */

import { NavLink, Outlet } from 'react-router';

import estilos from '@/features/casca/casca.module.css';

const ABAS = [
  { para: '/conversa', rotulo: 'Conversa' },
  { para: '/historico', rotulo: 'Histórico' },
  { para: '/conta', rotulo: 'Conta' },
  { para: '/configuracoes', rotulo: 'Configurações' },
] as const;

export function Casca() {
  return (
    <div className={estilos.casca}>
      <header className={estilos.topo}>
        <span className={estilos.marca}>Voicecoach</span>
        <nav className={estilos.navegacao} aria-label="Principal">
          {ABAS.map((aba) => (
            <NavLink
              key={aba.para}
              to={aba.para}
              className={({ isActive }) =>
                `${estilos.aba} ${isActive ? estilos.abaAtiva : ''}`
              }
            >
              {aba.rotulo}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className={estilos.conteudo}>
        <Outlet />
      </main>
    </div>
  );
}

export function TelaDeCarregamento() {
  return (
    <div className={estilos.carregandoTela} aria-busy="true">
      <span className="apoio">Carregando…</span>
    </div>
  );
}
