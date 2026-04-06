import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import LoginPage from './LoginPage';

vi.mock('./AuthContext', () => ({
  useAuth: () => ({
    login: vi.fn(),
  }),
}));

describe('LoginPage', () => {
  it('renders the updated product identity copy', () => {
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText('SessionFS')).toBeInTheDocument();
    expect(
      screen.getByText(/resume work, build project memory, and hand off ai sessions without losing context/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });
});
