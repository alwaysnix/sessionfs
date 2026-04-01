import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthContext';
import type { HelmLicense } from '../api/client';

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-green-500/10 text-green-500 border-green-500/30',
  expired: 'bg-red-500/10 text-red-500 border-red-500/30',
  revoked: 'bg-neutral-500/10 text-neutral-400 border-neutral-500/30',
  trial: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/30',
};

export default function LicensesTab() {
  const { auth } = useAuth();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('all');

  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-licenses', statusFilter],
    queryFn: () => auth!.client.adminListLicenses(statusFilter),
    enabled: !!auth,
  });

  const revokeMutation = useMutation({
    mutationFn: ({ key, reason }: { key: string; reason: string }) =>
      auth!.client.adminRevokeLicense(key, reason),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-licenses'] }),
  });

  const licenses = data?.licenses ?? [];

  return (
    <div>
      {/* Filter */}
      <div className="mb-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-[var(--surface)] border border-[var(--border)] rounded-lg px-3 py-2 text-sm text-[var(--text-secondary)] focus:outline-none focus:border-[var(--brand)]"
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="expired">Expired</option>
          <option value="revoked">Revoked</option>
        </select>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-500 text-sm">
          Failed to load licenses: {String(error)}
        </div>
      )}

      {isLoading && (
        <div className="text-[var(--text-tertiary)] text-sm py-4">Loading licenses...</div>
      )}

      {!isLoading && licenses.length === 0 && (
        <div className="text-center py-12 text-[var(--text-tertiary)] text-sm">No licenses found</div>
      )}

      {licenses.length > 0 && (
        <div className="border border-[var(--border)] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--bg-elevated)] text-[var(--text-tertiary)] text-xs uppercase tracking-wider">
                <th className="px-4 py-3 text-left">Organization</th>
                <th className="px-4 py-3 text-left">Contact</th>
                <th className="px-4 py-3 text-left w-20">Type</th>
                <th className="px-4 py-3 text-left w-20">Tier</th>
                <th className="px-4 py-3 text-center w-16">Seats</th>
                <th className="px-4 py-3 text-left w-24">Status</th>
                <th className="px-4 py-3 text-left w-28">Expires</th>
                <th className="px-4 py-3 text-center w-20">Actions</th>
              </tr>
            </thead>
            <tbody>
              {licenses.map((lic: HelmLicense) => {
                const statusStyle = STATUS_STYLES[lic.effective_status] || STATUS_STYLES['active'];
                return (
                  <tr
                    key={lic.id}
                    className="border-t border-[var(--border)] hover:bg-[var(--surface-hover)] transition-colors"
                  >
                    <td className="px-4 py-3 text-[var(--text-primary)]">{lic.org_name}</td>
                    <td className="px-4 py-3 text-[var(--text-secondary)]">{lic.contact_email}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-[var(--text-tertiary)]">{lic.license_type}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-[var(--text-secondary)] capitalize">{lic.tier}</span>
                    </td>
                    <td className="px-4 py-3 text-center text-[var(--text-secondary)] tabular-nums">
                      {lic.seats_limit}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 text-xs font-medium border rounded-full ${statusStyle}`}>
                        {lic.effective_status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-[var(--text-tertiary)]">
                      {lic.expires_at ? lic.expires_at.slice(0, 10) : 'Never'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {lic.effective_status === 'active' && (
                        <button
                          onClick={() => {
                            const reason = prompt('Reason for revocation:');
                            if (reason) revokeMutation.mutate({ key: lic.id, reason });
                          }}
                          disabled={revokeMutation.isPending}
                          className="text-xs text-red-500 hover:underline disabled:opacity-50"
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
