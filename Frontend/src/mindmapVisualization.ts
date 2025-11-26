/**
 * Mindmap Visualization Component
 * Creates a new window with particle background and mindmap content display
 */

export function showMindmapVisualization(mindmapContent: string, title: string = 'Mind Map') {
  const windowWidth = 1200
  const windowHeight = 800
  const screenX = (window.screen.width - windowWidth) / 2
  const screenY = (window.screen.height - windowHeight) / 2

  // Create a data URL for the mindmap HTML
  const mindmapHTML = `
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>${title}</title>
      <style>
        * {
          margin: 0;
          padding: 0;
          box-sizing: border-box;
        }

        body {
          font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
          overflow: hidden;
          height: 100vh;
          width: 100vw;
        }

        #canvas {
          position: fixed;
          left: 0;
          top: 0;
          width: 100%;
          height: 100%;
          background-color: #000000;
          z-index: 1;
        }

        #mindmap-content {
          position: fixed;
          left: 0;
          top: 0;
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          z-index: 2;
          padding: 40px;
          overflow-y: auto;
        }

        .mindmap-container {
          background: rgba(13, 13, 13, 0.85);
          border: 2px solid #ff8c00;
          border-radius: 16px;
          padding: 32px;
          max-width: 900px;
          width: 100%;
          box-shadow: 0 8px 32px rgba(255, 140, 0, 0.3);
          backdrop-filter: blur(10px);
        }

        .mindmap-title {
          color: #ff8c00;
          font-size: 28px;
          font-weight: 700;
          margin-bottom: 24px;
          text-align: center;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 12px;
        }

        .mindmap-content {
          color: #e0e0e0;
          line-height: 1.8;
          font-size: 15px;
        }

        .mindmap-content h1, .mindmap-content h2, .mindmap-content h3 {
          color: #ff8c00;
          margin: 20px 0 12px 0;
        }

        .mindmap-content h1 { font-size: 24px; }
        .mindmap-content h2 { font-size: 20px; }
        .mindmap-content h3 { font-size: 16px; }

        .mindmap-content strong {
          color: #ffa500;
        }

        .mindmap-content ul, .mindmap-content ol {
          margin: 12px 0 12px 24px;
        }

        .mindmap-content li {
          margin-bottom: 8px;
        }

        .mindmap-content code {
          background: #1a1a1a;
          padding: 2px 6px;
          border-radius: 4px;
          color: #ff8c00;
          font-family: monospace;
        }

        .mindmap-content pre {
          background: #1a1a1a;
          padding: 12px;
          border-radius: 6px;
          overflow-x: auto;
          margin: 12px 0;
          border-left: 3px solid #ff8c00;
        }

        .youtube-link {
          position: fixed;
          left: 20px;
          bottom: 20px;
          color: #fff;
          text-decoration: none;
          font-size: 12px;
          z-index: 10;
        }

        .youtube-link:hover {
          text-decoration: underline;
        }

        ::-webkit-scrollbar {
          width: 8px;
        }

        ::-webkit-scrollbar-track {
          background: transparent;
        }

        ::-webkit-scrollbar-thumb {
          background: #ff8c00;
          border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
          background: #ff6b00;
        }
      </style>
    </head>
    <body>
      <canvas id="canvas"></canvas>
      <div id="mindmap-content">
        <div class="mindmap-container">
          <div class="mindmap-title">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 2c1.657 0 3 1.343 3 3s-1.343 3-3 3-3-1.343-3-3 1.343-3 3-3z"></path>
              <path d="M6 9c1.657 0 3 1.343 3 3s-1.343 3-3 3-3-1.343-3-3 1.343-3 3-3z"></path>
              <path d="M18 9c1.657 0 3 1.343 3 3s-1.343 3-3 3-3-1.343-3-3 1.343-3 3-3z"></path>
              <path d="M15 17c1.657 0 3 1.343 3 3s-1.343 3-3 3-3-1.343-3-3 1.343-3 3-3z"></path>
              <path d="M9 17c1.657 0 3 1.343 3 3s-1.343 3-3 3-3-1.343-3-3 1.343-3 3-3z"></path>
              <line x1="12" y1="5" x2="6" y2="9"></line>
              <line x1="12" y1="5" x2="18" y2="9"></line>
              <line x1="6" y1="12" x2="9" y2="17"></line>
              <line x1="18" y1="12" x2="15" y2="17"></line>
            </svg>
            ${title}
          </div>
          <div class="mindmap-content" id="mindmap-text">${mindmapContent}</div>
        </div>
      </div>

      <script>
        let canvas = document.querySelector("#canvas");
        let ctx = canvas.getContext("2d");

        let w, h, particles;
        let particleDistance = 40;
        let mouse = {
          x: undefined,
          y: undefined,
          radius: 100
        }

        function init() {
          resizeReset();
          animationLoop();
        }

        function resizeReset() {
          w = canvas.width = window.innerWidth;
          h = canvas.height = window.innerHeight;

          particles = [];
          for (let y = (((h - particleDistance) % particleDistance) + particleDistance) / 2; y < h; y += particleDistance) {
            for (let x = (((w - particleDistance) % particleDistance) + particleDistance) / 2; x < w; x += particleDistance) {
              particles.push(new Particle(x, y));
            }
          }
        }

        function animationLoop() {
          ctx.clearRect(0, 0, w, h);
          drawScene();
          requestAnimationFrame(animationLoop);
        }

        function drawScene() {
          for (let i = 0; i < particles.length; i++) {
            particles[i].update();
            particles[i].draw();
          }
        }

        function mousemove(e) {
          mouse.x = e.x;
          mouse.y = e.y;
        }

        function mouseout() {
          mouse.x = undefined;
          mouse.y = undefined;
        }

        class Particle {
          constructor(x, y) {
            this.x = x;
            this.y = y;
            this.size = 2;
            this.baseX = this.x;
            this.baseY = this.y;
            this.speed = (Math.random() * 25) + 5;
          }
          draw() {
            ctx.fillStyle = "rgba(255, 140, 0, 0.5)";
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.closePath();
            ctx.fill();
          }
          update() {
            let dx = mouse.x - this.x;
            let dy = mouse.y - this.y;
            let distance = Math.sqrt(dx * dx + dy * dy);
            let maxDistance = mouse.radius;
            let force = (maxDistance - distance) / maxDistance;
            let forceDirectionX = dx / distance;
            let forceDirectionY = dy / distance;
            let directionX = forceDirectionX * force * this.speed;
            let directionY = forceDirectionY * force * this.speed;

            if (distance < mouse.radius) {
              this.x -= directionX;
              this.y -= directionY;
            } else {
              if (this.x !== this.baseX) {
                let dx = this.x - this.baseX;
                this.x -= dx / 10;
              }
              if (this.y !== this.baseY) {
                let dy = this.y - this.baseY;
                this.y -= dy / 10;
              }
            }
          }
        }

        init();
        window.addEventListener("resize", resizeReset);
        window.addEventListener("mousemove", mousemove);
        window.addEventListener("mouseout", mouseout);
      </script>
    </body>
    </html>
  `

  const blob = new Blob([mindmapHTML], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  const windowFeatures = `width=${windowWidth},height=${windowHeight},left=${screenX},top=${screenY}`
  window.open(url, 'mindmap', windowFeatures)

  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
