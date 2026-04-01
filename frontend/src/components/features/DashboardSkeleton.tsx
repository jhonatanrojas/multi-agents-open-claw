import { Skeleton, SkeletonCard } from '@/components/shared/Skeleton';
import './DashboardSkeleton.css';

export function DashboardSkeleton() {
  return (
    <div className="dashboard-skeleton">
      {/* Header */}
      <div className="skeleton-header-row">
        <div>
          <Skeleton width="200px" height="32px" />
          <Skeleton width="300px" height="16px" />
        </div>
        <Skeleton width="120px" height="36px" variant="rect" />
      </div>

      {/* Tabs */}
      <div className="skeleton-tabs-row">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton 
            key={i} 
            width="100px" 
            height="36px" 
            variant="rect" 
            className="skeleton-tab"
          />
        ))}
      </div>

      {/* Content Grid */}
      <div className="skeleton-content-grid">
        {/* Sidebar */}
        <div className="skeleton-sidebar">
          <Skeleton width="100%" height="24px" />
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton 
              key={i} 
              width="100%" 
              height="48px" 
            />
          ))}
        </div>

        {/* Main Content */}
        <div className="skeleton-main">
          <Skeleton width="60%" height="28px" />
          
          {/* Stats Row */}
          <div className="skeleton-stats">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>

          {/* Tasks List */}
          <Skeleton width="40%" height="24px" />
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton-task-item">
              <Skeleton width="40px" height="40px" variant="circle" />
              <div style={{ flex: 1 }}>
                <Skeleton width="60%" height="18px" />
                <Skeleton width="40%" height="14px" />
              </div>
              <Skeleton width="80px" height="24px" variant="rect" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function LoginForm() {
  return (
    <div className="login-skeleton">
      <div className="login-card">
        <Skeleton width="150px" height="32px" />
        <Skeleton width="250px" height="16px" />
        
        <Skeleton width="100%" height="20px" />
        <Skeleton width="100%" height="48px" variant="rect" />
        
        <Skeleton width="100%" height="48px" variant="rect" />
      </div>
    </div>
  );
}

export function ConnectingScreen() {
  return (
    <div className="connecting-screen">
      <div className="connecting-spinner-large" />
      <h3>Conectando al servidor...</h3>
      <p>Estableciendo conexión en tiempo real</p>
    </div>
  );
}
