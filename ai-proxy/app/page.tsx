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
          GLM AI Service with Text, Vision & Image Generation
        </p>
        
        <div style={{
          display: 'grid',
          gap: '15px',
          maxWidth: '450px',
          margin: '0 auto',
        }}>
          <div style={{
            padding: '15px',
            background: 'rgba(16, 185, 129, 0.1)',
            borderRadius: '8px',
            border: '1px solid rgba(16, 185, 129, 0.3)',
          }}>
            <h3 style={{ color: '#10b981', marginBottom: '8px' }}>💬 Text Chat API</h3>
            <code style={{ fontSize: '14px', color: '#e5e7eb' }}>POST /api/ai</code>
            <p style={{ fontSize: '12px', color: '#9ca3af', marginTop: '5px' }}>
              Generate text responses with GLM-4
            </p>
          </div>
          
          <div style={{
            padding: '15px',
            background: 'rgba(59, 130, 246, 0.1)',
            borderRadius: '8px',
            border: '1px solid rgba(59, 130, 246, 0.3)',
          }}>
            <h3 style={{ color: '#3b82f6', marginBottom: '8px' }}>👁️ Vision API</h3>
            <code style={{ fontSize: '14px', color: '#e5e7eb' }}>POST /api/ai/vision</code>
            <p style={{ fontSize: '12px', color: '#9ca3af', marginTop: '5px' }}>
              Analyze images with GLM-4V
            </p>
          </div>
          
          <div style={{
            padding: '15px',
            background: 'rgba(168, 85, 247, 0.1)',
            borderRadius: '8px',
            border: '1px solid rgba(168, 85, 247, 0.3)',
          }}>
            <h3 style={{ color: '#a855f7', marginBottom: '8px' }}>🎨 Image Generation</h3>
            <code style={{ fontSize: '14px', color: '#e5e7eb' }}>POST /api/image</code>
            <p style={{ fontSize: '12px', color: '#9ca3af', marginTop: '5px' }}>
              Generate images from text prompts
            </p>
          </div>
          
          <div style={{
            padding: '15px',
            background: 'rgba(245, 158, 11, 0.1)',
            borderRadius: '8px',
            border: '1px solid rgba(245, 158, 11, 0.3)',
          }}>
            <h3 style={{ color: '#f59e0b', marginBottom: '8px' }}>🔌 OpenAI Compatible</h3>
            <code style={{ fontSize: '14px', color: '#e5e7eb' }}>POST /api/chat/completions</code>
            <p style={{ fontSize: '12px', color: '#9ca3af', marginTop: '5px' }}>
              Drop-in OpenAI API replacement
            </p>
          </div>
        </div>

        <div style={{ marginTop: '30px', padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
          <h4 style={{ color: '#10b981', marginBottom: '10px' }}>📝 Quick Examples</h4>
          <div style={{ textAlign: 'left', fontSize: '12px', color: '#9ca3af' }}>
            <p><strong>Text:</strong> POST /api/ai {"{ messages: [{role: 'user', content: 'Hello'}] }"}</p>
            <p><strong>Vision:</strong> POST /api/ai/vision {"{ image_base64: '...', prompt: 'Describe' }"}</p>
            <p><strong>Image:</strong> POST /api/image {"{ prompt: 'A cat in space', size: '1024x1024' }"}</p>
          </div>
        </div>
        
        <p style={{ marginTop: '20px', color: '#6b7280', fontSize: '14px' }}>
          Running on port 3000 • Powered by z-ai-web-dev-sdk
        </p>
      </div>
    </main>
  );
}
