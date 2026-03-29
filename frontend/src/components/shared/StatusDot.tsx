import { STATUS_COLOR } from '@/constants';

interface StatusDotProps {
  connected: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function StatusDot({ connected, size = 'md' }: StatusDotProps) {
  const colors = connected ? STATUS_COLOR.working : STATUS_COLOR.offline;
  
  const sizeMap = {
    sm: '6px',
    md: '8px',
    lg: '10px',
  };

  return (
    <span
      style={{
        display: 'inline-block',
        width: sizeMap[size],
        height: sizeMap[size],
        borderRadius: '50%',
        backgroundColor: colors.dot,
        boxShadow: connected ? `0 0 6px ${colors.dot}` : 'none',
      }}
      title={connected ? 'Conectado' : 'Desconectado'}
    />
  );
}
