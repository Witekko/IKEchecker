document.addEventListener('DOMContentLoaded', function() {
    // 1. LOADER LOGIC
    const loader = document.getElementById('page-loader');

    // Pokaż loader przy kliknięciu w linki (chyba że to kotwica lub JS)
    document.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            const target = this.getAttribute('target');
            if (href && href !== '#' && !href.startsWith('#') && !href.includes('javascript') && target !== '_blank' && !href.includes('logout')) {
                if (loader) {
                    loader.style.display = 'flex';
                }
            }
        });
    });

    // Pokaż loader przy wysyłaniu formularzy
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', () => {
            if (loader) {
                loader.style.display = 'flex';
            }
        });
    });

    // 2. SIDEBAR DROPDOWN FIX (Zamykanie przy zwijaniu)
    const sidebar = document.querySelector('.sidebar-desktop');
    if (sidebar) {
        sidebar.addEventListener('mouseleave', function() {
            const openDropdowns = sidebar.querySelectorAll('.dropdown-toggle.show');
            openDropdowns.forEach(dropdownToggle => {
                const dropdownInstance = bootstrap.Dropdown.getInstance(dropdownToggle);
                if(dropdownInstance) dropdownInstance.hide();
            });
        });
    }
    
    // 3. TOOLTIPS INITIALIZATION
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // 4. FOOTER REVEAL ON SCROLL
    const footerEls = document.querySelectorAll('.footer-reveal');
    if (footerEls.length > 0) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('active');
                }
            });
        }, { threshold: 0.1 }); // Trigger when 10% visible
        
        footerEls.forEach(el => observer.observe(el));
    }

    // 5. BACKGROUND CHART ANIMATION (Aurora style)
    const canvas = document.getElementById('bg-chart-canvas');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        let width, height;

        const resize = () => {
            width = canvas.width = window.innerWidth;
            height = canvas.height = window.innerHeight;
        };
        window.addEventListener('resize', resize);
        resize();

        // 3 moving lines mimicking stock charts (Green, White, Red)
        const lines = [
            { yBase: 0.65, amp: 120, freq: 0.0015, speed: 0.006, color: 'rgba(0, 255, 127, 0.12)', offset: 0 },
            { yBase: 0.50, amp:  90, freq: 0.0025, speed: 0.008, color: 'rgba(255, 255, 255, 0.05)', offset: 50 },
            { yBase: 0.75, amp: 160, freq: 0.0010, speed: 0.004, color: 'rgba(239, 83, 80, 0.08)', offset: 120 }
        ];

        let time = 0;
        function draw() {
            ctx.clearRect(0, 0, width, height);

            lines.forEach(line => {
                ctx.beginPath();
                
                // Construct the chart line using combined sine waves for randomness
                for (let x = 0; x <= width + 50; x += 30) {
                    let y = height * line.yBase;
                    y += Math.sin(x * line.freq + time * line.speed + line.offset) * line.amp;
                    y += Math.sin(x * (line.freq * 2.2) + time * (line.speed * 1.5)) * (line.amp * 0.3); // secondary noise
                    y += Math.sin(x * (line.freq * 5.5)) * (line.amp * 0.05); // micro volatility
                    
                    if (x === 0) ctx.moveTo(x, y);
                    else ctx.lineTo(x, y);
                }

                ctx.strokeStyle = line.color;
                ctx.lineWidth = 2;
                ctx.stroke();

                // Fill area under the line with extreme transparency for aurora glow
                ctx.lineTo(width, height);
                ctx.lineTo(0, height);
                ctx.fillStyle = line.color.replace(/[\d\.]+\)$/g, '0.015)'); 
                ctx.fill();
            });

            time++;
            requestAnimationFrame(draw);
        }
        draw();
    }
});

// Ukryj loader po powrocie (cache przeglądarki)
window.addEventListener('pageshow', (e) => {
    if(e.persisted) document.getElementById('page-loader').style.display = 'none';
});