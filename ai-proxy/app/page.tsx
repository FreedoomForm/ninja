export default function Home() {
  return (
    <main style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
      color: '#fff',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    }}>
      <div style={{
        textAlign: 'center',
        padding: '40px',
        borderRadius: '16px',
        background: 'rgba(255,255,255,0.05)',
        backdropFilter: 'blur(10px)',
      }}>
        <h1 style={{ fontSize: '48px', marginBottom: '20px' }}>
          🥷 Ninja AI Proxy
        </h1>
        <p style={{ fontSize: '18px', color: '#9ca3af', marginBottom: '30px' }}>
          GLM AI Service for Telegram Userbot
        </p>
        
        <div style={{
          display: 'grid',
          gap: '15px',
          maxWidth: '400px',
          margin: '0 auto',
        }}>
          <div style={{
            padding: '15px',
            background: 'rgba(16, 185, 129, 0.1)',
            borderRadius: '8px',
            border: '1px solid rgba(16, 185, 129, 0.3)',
          }}>
            <h3 style={{ color: '#10b981', marginBottom: '8px' }}>💬 Chat API</h3>
            <code style={{ fontSize: '14px', color: '#e5e7eb' }}>POST /api/ai</code>
          </div>
          
          <div style={{
            padding: '15px',
            background: 'rgba(59, 130, 246, 0.1)',
            borderRadius: '8px',
            border: '1px solid rgba(59, 130, 246, 0.3)',
          }}>
            <h3 style={{ color: '#3b82f6', marginBottom: '8px' }}>🖼️ Vision API</h3>
            <code style={{ fontSize: '14px', color: '#e5e7eb' }}>POST /api/ai/vision</code>
          </div>
          
          <div style={{
            padding: '15px',
            background: 'rgba(245, 158, 11, 0.1)',
            borderRadius: '8px',
            border: '1px solid rgba(245, 158, 11, 0.3)',
          }}>
            <h3 style={{ color: '#f59e0b', marginBottom: '8px' }}>🔌 OpenAI Compatible</h3>
            <code style={{ fontSize: '14px', color: '#e5e7eb' }}>POST /api/chat/completions</code>
          </div>
        </div>
        
        <p style={{ marginTop: '30px', color: '#6b7280', fontSize: '14px' }}>
          Running on port 3000 • Connected to GLM-4
        </p>
      </div>
    </main>
  );
}
