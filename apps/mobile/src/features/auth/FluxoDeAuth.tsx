/**
 * O roteador das cinco telas de auth (CARD-050) — estado local, não rotas do
 * `expo-router`. Nenhuma delas precisa de URL própria (ninguém compartilha
 * link para "tela de login"), e um `useState` aqui é mais simples que um
 * grupo de rotas com guarda de navegação — a mesma disciplina anti-
 * overengineering da Parte F da visão, aplicada à navegação.
 */

import { useState } from 'react';

import { TelaCadastro } from '@/features/auth/TelaCadastro';
import { TelaConfirmeSeuEmail } from '@/features/auth/TelaConfirmeSeuEmail';
import { TelaEntrada } from '@/features/auth/TelaEntrada';
import { TelaEsqueciMinhaSenha } from '@/features/auth/TelaEsqueciMinhaSenha';
import { TelaRedefinirSenha } from '@/features/auth/TelaRedefinirSenha';

type Tela =
  | { nome: 'entrada' }
  | { nome: 'cadastro' }
  | { nome: 'confirme-email'; email: string }
  | { nome: 'esqueci-senha' }
  | { nome: 'redefinir-senha' };

export function FluxoDeAuth() {
  const [tela, setTela] = useState<Tela>({ nome: 'entrada' });

  switch (tela.nome) {
    case 'entrada':
      return (
        <TelaEntrada
          aoIrParaCadastro={() => setTela({ nome: 'cadastro' })}
          aoIrParaEsqueciSenha={() => setTela({ nome: 'esqueci-senha' })}
        />
      );
    case 'cadastro':
      return (
        <TelaCadastro
          aoRegistrar={(email) => setTela({ nome: 'confirme-email', email })}
          aoIrParaEntrada={() => setTela({ nome: 'entrada' })}
        />
      );
    case 'confirme-email':
      return (
        <TelaConfirmeSeuEmail
          email={tela.email}
          aoVoltarParaEntrada={() => setTela({ nome: 'entrada' })}
        />
      );
    case 'esqueci-senha':
      return (
        <TelaEsqueciMinhaSenha
          aoJaTerOCodigo={() => setTela({ nome: 'redefinir-senha' })}
          aoVoltarParaEntrada={() => setTela({ nome: 'entrada' })}
        />
      );
    case 'redefinir-senha':
      return (
        <TelaRedefinirSenha
          aoConcluir={() => setTela({ nome: 'entrada' })}
          aoVoltarParaEntrada={() => setTela({ nome: 'entrada' })}
        />
      );
  }
}
