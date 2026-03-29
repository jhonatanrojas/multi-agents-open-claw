import { useMemoryStore } from '@/store';
import type { Blocker } from '@/types';

export function BlockersBar() {
  const blockers = useMemoryStore((state) => state.blockers);

  if (blockers.length === 0) {
    return null;
  }

  return (
    <div
      className="blockers-bar"
      style={{
        padding: '12px 16px',
        backgroundColor: '#3a2a2a',
        borderRadius: '8px',
        borderLeft: '3px solid #e24b4a',
        marginBottom: '16px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '8px',
        }}
      >
        <span style={{ fontSize: '1rem' }}>🚫</span>
        <span
          style={{
            fontWeight: 600,
            fontSize: '0.85rem',
            color: '#e88',
          }}
        >
          Bloqueadores activos ({blockers.length})
        </span>
      </div>
      <ul
        style={{
          margin: 0,
          paddingLeft: '24px',
          fontSize: '0.8rem',
          color: '#caa',
        }}
      >
        {blockers.map((blocker: Blocker, i: number) => (
          <li key={i} style={{ marginBottom: '4px' }}>
            <span style={{ fontWeight: 600, color: '#e99' }}>{blocker.source}:</span>{' '}
            {blocker.msg}
          </li>
        ))}
      </ul>
    </div>
  );
}
