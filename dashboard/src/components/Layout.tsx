import { useState, useRef, useEffect } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useHandoffInbox } from '../hooks/useHandoffs';
import { useMe } from '../hooks/useMe';
import SearchBar from './SearchBar';
import ThemeToggle from './ThemeToggle';
import { Badge } from './Badge';

const NAV_LINKS = [
  { to: '/', label: 'Sessions', match: (p: string) => p === '/' },
  { to: '/handoffs', label: 'Handoffs', match: (p: string) => p.startsWith('/handoffs') },
  { to: '/settings', label: 'Settings', match: (p: string) => p.startsWith('/settings') && p !== '/settings/billing' },
  { to: '/settings/billing', label: 'Billing', match: (p: string) => p === '/settings/billing' },
];

export default function Layout() {
  const { logout } = useAuth();
  const location = useLocation();
  const inbox = useHandoffInbox();
  const me = useMe();
  const isAdmin = me.data?.tier === 'admin';
  const pendingCount = inbox.data?.handoffs.filter((h) => h.status === 'pending').length ?? 0;

  const [avatarOpen, setAvatarOpen] = useState(false);
  const avatarRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (avatarRef.current && !avatarRef.current.contains(e.target as Node)) {
        setAvatarOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const tierLabel = me.data?.tier || 'free';
  const tierVariant = tierLabel === 'admin' ? 'info' : tierLabel === 'team' ? 'success' : 'default';
  const userInitial = (me.data?.email?.[0] || 'U').toUpperCase();

  return (
    <div className="flex flex-col min-h-screen">
      <header
        className="flex items-center justify-between px-5"
        style={{
          height: 56,
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'var(--bg-primary)',
        }}
      >
        {/* Left: Logo */}
        <Link to="/" className="flex items-center shrink-0 hover:opacity-90 transition-opacity">
          <span
            className="text-[17px] font-semibold tracking-tight"
            style={{ color: 'var(--text-primary)' }}
          >
            Session<span style={{ color: 'var(--brand)' }}>FS</span>
          </span>
        </Link>

        {/* Center: Nav links */}
        <nav className="flex items-center gap-1 text-[14px]">
          {NAV_LINKS.map(({ to, label, match }) => {
            const active = match(location.pathname);
            return (
              <Link
                key={to}
                to={to}
                className="relative px-3 py-1.5 rounded-[var(--radius-sm)] transition-colors"
                style={{
                  color: active ? 'var(--brand)' : 'var(--text-secondary)',
                }}
                onMouseEnter={(e) => {
                  if (!active) e.currentTarget.style.color = 'var(--text-primary)';
                }}
                onMouseLeave={(e) => {
                  if (!active) e.currentTarget.style.color = 'var(--text-secondary)';
                }}
              >
                {label}
                {label === 'Handoffs' && pendingCount > 0 && (
                  <span
                    className="ml-1 px-1.5 py-0.5 text-xs rounded-full font-medium"
                    style={{
                      backgroundColor: 'rgba(240,192,64,0.15)',
                      color: 'var(--warning)',
                    }}
                  >
                    {pendingCount}
                  </span>
                )}
                {active && (
                  <span
                    className="absolute bottom-0 left-3 right-3 h-0.5 rounded-full"
                    style={{ backgroundColor: 'var(--brand)' }}
                  />
                )}
              </Link>
            );
          })}
          {isAdmin && (
            <Link
              to="/admin"
              className="relative px-3 py-1.5 rounded-[var(--radius-sm)] transition-colors"
              style={{
                color: location.pathname === '/admin' ? 'var(--brand)' : 'var(--text-secondary)',
              }}
              onMouseEnter={(e) => {
                if (location.pathname !== '/admin') e.currentTarget.style.color = 'var(--text-primary)';
              }}
              onMouseLeave={(e) => {
                if (location.pathname !== '/admin') e.currentTarget.style.color = 'var(--text-secondary)';
              }}
            >
              Admin
              {location.pathname === '/admin' && (
                <span
                  className="absolute bottom-0 left-3 right-3 h-0.5 rounded-full"
                  style={{ backgroundColor: 'var(--brand)' }}
                />
              )}
            </Link>
          )}
          <SearchBar />
        </nav>

        {/* Right: ThemeToggle + Avatar */}
        <div className="flex items-center gap-2 shrink-0">
          <ThemeToggle />
          <div className="relative" ref={avatarRef}>
            <button
              onClick={() => setAvatarOpen((v) => !v)}
              className="flex items-center gap-2 rounded-[var(--radius-md)] px-2 py-1 transition-colors hover:bg-[var(--surface-hover)]"
            >
              <span
                className="flex items-center justify-center w-7 h-7 rounded-full text-xs font-semibold"
                style={{
                  backgroundColor: 'var(--brand)',
                  color: 'var(--text-inverse)',
                }}
              >
                {userInitial}
              </span>
              <Badge variant={tierVariant as 'default' | 'success' | 'info'} label={tierLabel} size="sm" />
            </button>
            {avatarOpen && (
              <div
                className="absolute right-0 mt-1 w-40 py-1 rounded-[var(--radius-md)] border z-50"
                style={{
                  backgroundColor: 'var(--bg-elevated)',
                  borderColor: 'var(--border)',
                  boxShadow: 'var(--shadow-md)',
                }}
              >
                <button
                  onClick={() => {
                    setAvatarOpen(false);
                    logout();
                  }}
                  className="w-full text-left px-3 py-1.5 text-sm transition-colors hover:bg-[var(--surface-hover)]"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}
