document.addEventListener('DOMContentLoaded', function() {
    const ctx = document.getElementById('assetChart');
    if (!ctx) return;

    // Pobieranie danych z JSON Islands
    function getData(id) {
        try { return JSON.parse(document.getElementById(id).textContent); }
        catch (e) { return []; }
    }

    const masterDates = getData('c-dates');
    const masterPrices = getData('c-prices');
    const masterColors = getData('c-colors');
    const masterRadius = getData('c-radius');
    const firstTradeDate = getData('first-trade-date');
    const valATH = getData('val-ath');
    const valATL = getData('val-atl');

    let assetChart = null;
    let currentStartPrice = null;

    // Znajdź indeks pierwszej transakcji (gdzie radius > 0)
    let firstTradeIndex = masterRadius.findIndex(r => r > 0);
    if (firstTradeIndex === -1) firstTradeIndex = 0;

    // Plugin do rysowania linii ATH/ATL
    const horizontalLinesPlugin = {
        id: 'horizontalLines',
        afterDraw: (chart) => {
            const ctx = chart.ctx;
            const yScale = chart.scales.y;
            const chartArea = chart.chartArea;

            ctx.save();
            ctx.lineWidth = 1;
            ctx.font = '10px sans-serif';

            function drawLine(value, color, text, isDashed = true) {
                const y = yScale.getPixelForValue(value);
                if(y < chartArea.top || y > chartArea.bottom) return;

                ctx.beginPath();
                ctx.strokeStyle = color;
                if(isDashed) ctx.setLineDash([5, 5]);
                else ctx.setLineDash([2, 4]);

                ctx.moveTo(chartArea.left, y);
                ctx.lineTo(chartArea.right, y);
                ctx.stroke();

                ctx.fillStyle = color;
                ctx.fillText(text + ' (' + value.toFixed(2) + ')', chartArea.right - 80, y - 5);
            }

            if (valATH) drawLine(valATH, '#00ff7f', 'ATH');
            if (valATL) drawLine(valATL, '#ff4d4d', 'ATL');
            if (currentStartPrice !== null) drawLine(currentStartPrice, '#888', 'Ref', false);

            ctx.restore();
        }
    };

    function getStartIndexForRange(range) {
        const totalPoints = masterDates.length;

        if (range === 'SINCE_BUY') {
            // Jeśli mamy datę pierwszej transakcji, szukamy jej indeksu
            if (firstTradeDate) {
                const idx = masterDates.indexOf(firstTradeDate);
                // Cofamy się o 3 dni dla kontekstu, ale nie mniej niż 0
                return (idx !== -1) ? Math.max(0, idx - 3) : 0;
            }
            return 0; // Fallback
        }

        // Logika YTD
        if (range === 'YTD') {
            const currentYear = new Date().getFullYear();
            const ytdDateStr = currentYear + '-01-01';
            const idx = masterDates.findIndex(d => d >= ytdDateStr);
            return (idx !== -1) ? idx : 0;
        }

        let sliceCount = totalPoints;
        if (range === '1M') sliceCount = 21;
        else if (range === '3M') sliceCount = 63;
        else if (range === '1Y') sliceCount = 252;

        if (sliceCount > totalPoints) sliceCount = totalPoints;
        return totalPoints - sliceCount;
    }

    function updateDynamicTile(range, startIndex) {
        const lbl = document.getElementById('dynamic-label');
        const val = document.getElementById('dynamic-value');
        const sub = document.getElementById('dynamic-sub');
        if(!lbl || !val || !sub) return;

        lbl.innerText = range.replace('_', ' ') + " Change %";

        if (masterPrices.length > 0) {
            const startPrice = masterPrices[startIndex];
            const endPrice = masterPrices[masterPrices.length - 1];

            if (startPrice && startPrice > 0) {
                const diff = endPrice - startPrice;
                const pct = (diff / startPrice) * 100;
                const sign = pct >= 0 ? '+' : '';
                const colorClass = pct >= 0 ? 'text-success' : 'text-danger';

                val.className = `fw-bold mb-0 ${colorClass}`;
                val.innerText = `${sign}${pct.toFixed(2)}%`;
                sub.innerText = `Price: ${startPrice.toFixed(2)} -> ${endPrice.toFixed(2)}`;
            } else {
                val.innerText = "N/A";
            }
        }
    }

    function initChart() {
        const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 450);
        gradient.addColorStop(0, 'rgba(0, 255, 127, 0.2)');
        gradient.addColorStop(1, 'rgba(0, 255, 127, 0.0)');

        const initialRange = 'SINCE_BUY';
        const chartStartIndex = getStartIndexForRange(initialRange);

        currentStartPrice = masterPrices[chartStartIndex];

        // Dla kafelka Period Change, jeśli SINCE_BUY to bierzemy od pierwszej transakcji
        let mathStartIndex = chartStartIndex;
        if (initialRange === 'SINCE_BUY') mathStartIndex = firstTradeIndex;

        updateDynamicTile(initialRange, mathStartIndex);

        assetChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: masterDates.slice(chartStartIndex),
                datasets: [{
                    label: 'Price (PLN)',
                    data: masterPrices.slice(chartStartIndex),
                    borderColor: '#00ff7f',
                    backgroundColor: gradient,
                    borderWidth: 2,
                    pointBackgroundColor: masterColors.slice(chartStartIndex),
                    pointBorderColor: '#fff',
                    pointRadius: masterRadius.slice(chartStartIndex),
                    pointHoverRadius: 8,
                    fill: true,
                    tension: 0.2
                }]
            },
            plugins: [horizontalLinesPlugin],
            options: {
                responsive: true, maintainAspectRatio: false, animation: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(30,30,30,0.95)',
                        titleColor: '#fff', bodyColor: '#ccc', borderColor: '#444', borderWidth: 1, padding: 10, displayColors: false
                    }
                },
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#666', maxTicksLimit: 8 } },
                    y: { grid: { color: '#333', borderDash: [4, 4] }, ticks: { color: '#a0a0a0' } }
                }
            }
        });
    }

    // Export funkcji do globalnego scope (żeby przyciski działały)
    window.updateChartRange = function(range) {
        if (!assetChart) return;

        document.querySelectorAll('.btn-group button').forEach(btn => {
            btn.classList.remove('active');
            if(btn.innerText === range.replace('_', ' ')) btn.classList.add('active');
        });

        const chartStartIndex = getStartIndexForRange(range);

        assetChart.data.labels = masterDates.slice(chartStartIndex);
        assetChart.data.datasets[0].data = masterPrices.slice(chartStartIndex);
        assetChart.data.datasets[0].pointBackgroundColor = masterColors.slice(chartStartIndex);
        assetChart.data.datasets[0].pointRadius = masterRadius.slice(chartStartIndex);

        currentStartPrice = masterPrices[chartStartIndex];
        assetChart.update();

        let mathStartIndex = chartStartIndex;
        if (range === 'SINCE_BUY' || range === 'MAX') {
            mathStartIndex = firstTradeIndex;
        }
        updateDynamicTile(range, mathStartIndex);
    };

    initChart();
});