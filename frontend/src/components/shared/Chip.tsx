interface ChipProps {
  children: React.ReactNode;
  bg?: string;
  color?: string;
  size?: 'sm' | 'md';
}

export function Chip({ 
  children, 
  bg = '#EEEDFE', 
  color = '#3C3489',
  size = 'sm' 
}: ChipProps) {
  const padding = size === 'sm' ? '2px 8px' : '4px 12px';
  const fontSize = size === 'sm' ? '0.75rem' : '0.875rem';

  return (
    <span
      className="chip"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding,
        fontSize,
        borderRadius: '12px',
        backgroundColor: bg,
        color,
        fontWeight: 500,
        whiteSpace: 'nowrap' as const,
      }}
    >
      {children}
    </span>
  );
}
