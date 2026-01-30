document.addEventListener('DOMContentLoaded', function() {

        function gd(id) {
            const el = document.getElementById(id);
            if (!el) return [];
            try { return JSON.parse(el.textContent); }
            catch (e) { console.error('JSON Error:', id); return []; }
        }

        // Kolory awaryjne (gdyby backend zawiódł)
        const PIE_COLORS = ['#4DB6AC', '#7986CB', '#FFB74D', '#E0E0E0', '#BA68C8'];
        const NEON_GREEN = '#00ff7f';
        const SOFT_RED = '#ef5350';
        const MAIN_COLOR = '#00ff7f';

        // --- ALLOCATION CHART (Z NAPRAWIONYMI KOLORAMI) ---
        const ctxAlloc = document.getElementById('allocationChart');
        let allocChartInstance = null;

        if (ctxAlloc) {
            // Pobieramy dane ORAZ KOLORY
            const allocData = {
                'asset': {
                    labels: gd('l-alloc'),
                    values: gd('d-alloc'),
                    colors: gd('d-colors') // Kolory cieniowane z Pythona
                },
                'sector': {
                    labels: gd('l-sec'),
                    values: gd('d-sec'),
                    colors: gd('d-sec-col') // Kolory sektorów
                },
                'type': {
                    labels: gd('l-typ'),
                    values: gd('d-typ'),
                    colors: gd('d-typ-col') // Kolory typów
                }
            };

            function renderAllocChart(mode) {
                if (allocChartInstance) allocChartInstance.destroy();
                const d = allocData[mode];

                // Fallback, jeśli dane są puste
                if (!d || !d.values || d.values.length === 0) return;

                // Ustalanie kolorów: Jeśli backend przysłał, użyj ich. Jak nie - fallback.
                const bgColors = (d.colors && d.colors.length > 0) ? d.colors : PIE_COLORS;

                const totalPortfolio = d.values.reduce((a, b) => a + b, 0);
                const labelsWithPercent = d.labels.map((label, index) => {
                    const value = d.values[index];
                    const percent = totalPortfolio > 0 ? ((value / totalPortfolio) * 100).toFixed(1) : 0;
                    return `${label} (${percent}%)`;
                });

                allocChartInstance = new Chart(ctxAlloc, {
                    type: 'doughnut',
                    data: {
                        labels: labelsWithPercent,
                        datasets: [{
                            data: d.values,
                            backgroundColor: bgColors, // <--- TUTAJ WCHODZĄ TWOJE NOWE KOLORY
                            borderWidth: 0,
                            hoverOffset: 10
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: '70%',
                        plugins: {
                            legend: {
                                position: 'right',
                                labels: { color: '#e0e0e0', usePointStyle: true, boxWidth: 10, padding: 15, font: { size: 11 } }
                            },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        let label = context.label || '';
                                        let value = context.raw;
                                        return ` ${label}: ${value.toFixed(2)} PLN`;
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // Obsługa guzików
            const btnGroup = document.getElementById('alloc-btn-group');
            if(btnGroup) {
                btnGroup.querySelectorAll('.btn').forEach(btn => {
                    btn.addEventListener('click', function() {
                        btnGroup.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
                        this.classList.add('active');
                        renderAllocChart(this.getAttribute('data-mode'));
                    });
                });
            }

            // Start
            renderAllocChart('asset');
        }

        // --- RESZTA WYKRESÓW (Profit, Timeline, WinRate) ---
        // (Kod bez zmian, wklejam skrótowo żeby zamknąć blok)

        function filterTx(type, btn) {
            document.querySelectorAll('#txFilters .nav-link').forEach(b => b.classList.remove('active', 'text-white'));
            document.querySelectorAll('#txFilters .nav-link').forEach(b => b.classList.add('text-muted'));
            btn.classList.add('active', 'text-white');
            btn.classList.remove('text-muted');
            const rows = document.querySelectorAll('#txTable tbody tr');
            rows.forEach(row => {
                const rowType = row.getAttribute('data-type');
                let show = (type === 'ALL') ? true :
                           (type === 'BUY' && (rowType.includes('BUY'))) ? true :
                           (type === 'SELL' && (rowType.includes('SELL') || rowType === 'CLOSE')) ? true :
                           (type === 'DIVIDEND' && rowType === 'DIVIDEND') ? true : false;
                row.style.display = show ? '' : 'none';
            });
        }
        window.filterTx = filterTx; // Export do HTML

        // Win Rate
        const wins = gd('p-wins'); const losses = gd('p-losses');
        const ctxWin = document.getElementById('winRateChart');
        if (ctxWin && (wins + losses > 0)) {
            new Chart(ctxWin, {
                type: 'doughnut', data: { labels: ['Wins', 'Losses'], datasets: [{ data: [wins, losses], backgroundColor: [NEON_GREEN, SOFT_RED], borderWidth: 0, hoverOffset: 5 }] },
                options: { maintainAspectRatio: false, cutout: '80%', plugins: { legend: { display: false } } }
            });
        }

        // Timeline
        let mainChartInstance = null;
        const chartData = {
            dates: gd('t-dates'),
            value: { label: 'PLN', user: gd('t-user'), inv: gd('t-inv'), points: gd('t-points'), wig: gd('t-wig'), sp500: gd('t-sp500'), acwi: gd('t-acwi') },
            percent: { label: '%', user: gd('p-user'), wig: gd('p-wig'), sp500: gd('p-sp500'), acwi: gd('p-acwi'), inf: gd('p-inf') }
        };

        function renderMainChart(mode) {
            const ctx = document.getElementById('timelineChart');
            if(!ctx) return;
            if (mainChartInstance) mainChartInstance.destroy();
            const ctx2d = ctx.getContext('2d');
            const gradient = ctx2d.createLinearGradient(0, 0, 0, 400);
            gradient.addColorStop(0, 'rgba(0, 255, 127, 0.2)');
            gradient.addColorStop(1, 'rgba(0, 255, 127, 0.0)');

            if (mode === 'value') {
                datasets = [
                    { label: 'Portfolio', data: chartData.value.user, borderColor: MAIN_COLOR, backgroundColor: gradient, borderWidth: 2, fill: true, pointRadius: chartData.value.points, pointBackgroundColor: '#fff' },
                    { label: 'Invested', data: chartData.value.inv, borderColor: '#666', borderWidth: 2, borderDash:[4,4], fill:false, pointRadius:0 }
                ];
            } else {
                const sp500Data = chartData.percent.sp500 || [];


                datasets = [
                    { label: 'Portfolio %', data: chartData.percent.user, borderColor: MAIN_COLOR, backgroundColor: gradient, borderWidth: 2, fill: true, pointRadius: 0 },
                    { label: 'S&P 500 ETF (SPY)', data: chartData.percent.sp500, borderColor: '#42A5F5', borderWidth: 2, borderDash: [3, 3], fill: false, pointRadius: 0, tension: 0.1 },
                    { label: 'Global ETF (ACWI)', data: chartData.percent.acwi, borderColor: '#AB47BC', borderWidth: 2, borderDash: [3, 3], fill: false, pointRadius: 0, tension: 0.1 },
                    { label: 'Inflation', data: chartData.percent.inf, borderColor: '#ef5350', borderWidth: 2, borderDash: [2, 2], fill: false, pointRadius: 0, tension: 0.1 }
                ];
            }
            
            mainChartInstance = new Chart(ctx, {
                type: 'line', 
                data: { labels: chartData.dates, datasets: datasets },
                options: { 
                    responsive:true, 
                    maintainAspectRatio:false, 
                    interaction: { mode: 'index', intersect: false }, 
                    scales:{ x: { display: false }, y: { grid: { color: '#333' } } }, 
                    plugins:{ 
                        legend: { 
                            display: true,
                            labels: { color: '#e0e0e0', font: { size: 15, weight: 'bold' }, boxWidth: 20, padding: 25 }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    let value = context.parsed.y;
                                    if (mode === 'value') {
                                        return label + ': ' + value.toFixed(2) + ' PLN';
                                    } else {
                                        return label + ': ' + value.toFixed(2) + '%';
                                    }
                                }
                            }
                        }
                    } 
                }
            });
        }
        window.switchMainChart = function(mode) {
            const btnVal = document.getElementById('btn-val'); const btnPct = document.getElementById('btn-pct');
            if(mode==='value') { 
                btnVal.classList.add('active'); btnPct.classList.remove('active'); 
                document.getElementById('chart-title').textContent = 'Portfolio Value vs Invested Capital';
            }
            else { 
                btnPct.classList.add('active'); btnVal.classList.remove('active'); 
                document.getElementById('chart-title').textContent = 'ROI vs Market Benchmarks';
            }
            renderMainChart(mode);
        }
        if(chartData.dates.length > 0) renderMainChart('value');

        // Profit Chart
        const lPr = gd('l-prof');
        if(lPr.length>0) {
            new Chart(document.getElementById('profitChart'), {
                type:'bar', data:{ labels:lPr, datasets:[{ label:'Gain/Loss', data:gd('d-prof'), backgroundColor:gd('d-prof').map(v=>v>=0? NEON_GREEN : SOFT_RED), borderRadius: 4 }] },
                options: { maintainAspectRatio:false, scales: { x: { display: false }, y: { grid: { color: '#333' } } }, plugins: { legend: { display: false } } }
            });
        }
    });