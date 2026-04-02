import './Skeleton.css';

interface SkeletonProps {
  width?: string;
  height?: string;
  variant?: 'text' | 'rect' | 'circle';
  animation?: 'pulse' | 'wave' | 'none';
  className?: string;
  style?: React.CSSProperties;
}

export function Skeleton({ 
  width = '100%', 
  height = '20px', 
  variant = 'rect',
  animation = 'pulse',
  className = '',
  style
}: SkeletonProps) {
  return (
    <div 
      className={`skeleton skeleton-${variant} skeleton-${animation} ${className}`}
      style={{ width, height, ...style }}
      aria-hidden="true"
    />
  );
}

// Pre-configured skeleton layouts
export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton 
          key={i} 
          width={i === lines - 1 ? '70%' : '100%'} 
          height="16px" 
          variant="text" 
        />
      ))}
    </div>
  );
}

export function SkeletonCard() {
  return (
    <div style={{ padding: '16px', border: '1px solid #e0e0e0', borderRadius: '8px' }}>
      <Skeleton width="60%" height="24px" style={{ marginBottom: '12px' }} />
      <SkeletonText lines={2} />
    </div>
  );
}

export function SkeletonAvatar({ size = '40px' }: { size?: string }) {
  return <Skeleton width={size} height={size} variant="circle" />;
}
