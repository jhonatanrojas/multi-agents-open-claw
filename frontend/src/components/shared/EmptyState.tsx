interface EmptyStateProps {
  message: string;
  icon?: string;
}

export function EmptyState({ message, icon = '📭' }: EmptyStateProps) {
  return (
    <div
      className="empty-state"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 24px',
        textAlign: 'center',
        color: '#888',
        gap: '12px',
      }}
    >
      <span style={{ fontSize: '3rem', opacity: 0.5 }}>{icon}</span>
      <p
        style={{
          margin: 0,
          fontSize: '0.9rem',
          maxWidth: '280px',
          lineHeight: 1.5,
        }}
      >
        {message}
      </p>
    </div>
  );
}
