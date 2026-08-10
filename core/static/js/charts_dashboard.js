document.addEventListener('DOMContentLoaded', function() {
    const ChartDefaults = {
        font: {
            legendMain: 15,
            legendSmall: 11,
            labels: 12
        },
        colors: {
            text: '#e0e0e0',
            grid: '#333'
        },
        layout: {
            padding: 25,
            boxMain: 20,
            boxSmall: 10
        },
        tooltip: {
            backgroundColor: 'rgba(20, 20, 20, 0.95)',
            titleColor: '#00ff7f',
            bodyColor: '#e0e0e0',
            borderColor: 'rgba(0, 255, 127, 0.2)',
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8,
            titleFont: { size: 14, weight: 'bold' },
            bodyFont: { size: 13 },
            displayColors: true,
            boxPadding: 6
        },
        animation: {
            duration: 2000,
            easing: 'easeOutQuart'
        }
    };

    const PIE_COLORS = ['#4DB6AC', '#7986CB', '#FFB74D', '#E0E0E0', '#BA68C8'];
    const NEON_GREEN = '#00ff7f';
    const SOFT_RED = '#ef5350';
    const MAIN_COLOR = '#00ff7f';

    // Fetch API URL (with current query string for range selection)
    const apiUrl = '/dashboard/api/data/' + window.location.search;

    fetch(apiUrl)
        .then(response => response.json())
        .then(data => {
            // 1. Initialize CountUp on Stats Tiles
            if (typeof countUp !== 'undefined') {
                const options = {
                    decimalPlaces: 2,
                    duration: 1.5,
                    useGrouping: true,
                    separator: ' ',
                    decimal: '.'
                };
                
                const initCU = (id, val, prefix = '') => {
                    const el = document.getElementById(id);
                    if (el && !isNaN(val)) {
                        let cuOptions = { ...options, prefix: prefix };
                        let cu = new countUp.CountUp(id, val, cuOptions);
                        if (!cu.error) cu.start();
                    }
                };

                initCU('cu-total-value', parseFloat(data.tile_value_raw || 0));
                
                const valProfit = parseFloat(data.tile_total_profit_raw || 0);
                const valReturn = parseFloat(data.tile_return_pct_raw || 0);
                
                // Adjust colors for Profit & Return
                const profitContainer = document.getElementById('val-total-profit-container');
                if (profitContainer) {
                    if (valProfit >= 0) {
                        profitContainer.className = 'mb-0 fw-bold text-success';
                    } else {
                        profitContainer.className = 'mb-0 fw-bold text-danger';
                    }
                }
                const returnContainer = document.getElementById('val-return-pct-container');
                if (returnContainer) {
                    if (valReturn >= 0) {
                        returnContainer.className = 'mb-0 fw-bold text-success';
                    } else {
                        returnContainer.className = 'mb-0 fw-bold text-danger';
                    }
                }

                initCU('cu-total-profit', valProfit, valProfit > 0 ? '+' : '');
                initCU('cu-return-pct', valReturn, valReturn > 0 ? '+' : '');
                
                const valTwr = parseFloat(data.tile_twr || 0);
                const valMwr = parseFloat(data.tile_mwr || 0);
                
                const twrContainer = document.getElementById('val-twr');
                if (twrContainer) {
                    if (valTwr >= 0) {
                        twrContainer.className = 'mb-0 fw-bold text-success';
                    } else {
                        twrContainer.className = 'mb-0 fw-bold text-danger';
                    }
                }
                const mwrContainer = document.getElementById('val-mwr');
                if (mwrContainer) {
                    if (valMwr >= 0) {
                        mwrContainer.className = 'mb-0 fw-bold text-success';
                    } else {
                        mwrContainer.className = 'mb-0 fw-bold text-danger';
                    }
                }
                
                initCU('cu-twr', valTwr);
                initCU('cu-mwr', valMwr);
                
                const valUnrealized = parseFloat(data.tile_current_profit_raw || 0);
                const valRealized = parseFloat(data.tile_realized_raw || 0);
                const valDividends = parseFloat(data.tile_dividends_raw || 0);
                
                const unrealizedContainer = document.getElementById('val-unrealized');
                if (unrealizedContainer) {
                    if (valUnrealized >= 0) {
                        unrealizedContainer.className = 'mb-0 fw-bold text-success';
                    } else {
                        unrealizedContainer.className = 'mb-0 fw-bold text-danger';
                    }
                }
                const realizedContainer = document.getElementById('val-realized');
                if (realizedContainer) {
                    if (valRealized >= 0) {
                        realizedContainer.className = 'mb-0 fw-bold text-success';
                    } else {
                        realizedContainer.className = 'mb-0 fw-bold text-danger';
                    }
                }
                
                initCU('cu-unrealized', valUnrealized);
                initCU('cu-realized', valRealized, valRealized > 0 ? '+' : '');
                initCU('cu-dividends', valDividends, valDividends > 0 ? '+' : '');
                
                // 1D Stats
                const valDayPct = parseFloat(data.tile_day_pct_raw || 0);
                const valDayPln = parseFloat(data.tile_day_pln_raw || 0);
                
                const dayPctContainer = document.getElementById('val-day-pct-container');
                if (dayPctContainer) {
                    if (valDayPct >= 0) {
                        dayPctContainer.className = 'fw-bold fs-5 text-success';
                        dayPctContainer.innerHTML = `<i class="fas fa-caret-up text-accent me-1"></i><span id="cu-day-pct">0.00</span>%`;
                    } else {
                        dayPctContainer.className = 'fw-bold fs-5 text-danger';
                        dayPctContainer.innerHTML = `<i class="fas fa-caret-down text-danger me-1"></i><span id="cu-day-pct">0.00</span>%`;
                    }
                }
                const dayPlnContainer = document.getElementById('val-day-pln-container');
                if (dayPlnContainer) {
                    if (valDayPln >= 0) {
                        dayPlnContainer.className = 'fw-bold fs-5 text-success';
                        dayPlnContainer.innerHTML = `<span id="cu-day-pln">0.00</span> <span class="small text-muted">${data.tile_value_str ? data.tile_value_str.split(' ').pop() : 'PLN'}</span>`;
                    } else {
                        dayPlnContainer.className = 'fw-bold fs-5 text-danger';
                        dayPlnContainer.innerHTML = `<span id="cu-day-pln">0.00</span> <span class="small text-muted">${data.tile_value_str ? data.tile_value_str.split(' ').pop() : 'PLN'}</span>`;
                    }
                }
                
                initCU('cu-day-pct', valDayPct, valDayPct > 0 ? '+' : '');
                initCU('cu-day-pln', valDayPln, valDayPln > 0 ? '+' : '');
                
                const valGainers = parseFloat(data.tile_gainers || 0);
                const valLosers = parseFloat(data.tile_losers || 0);
                
                initCU('cu-gainers', valGainers);
                initCU('cu-losers', valLosers);
            }

            // 2. Initialize Tooltips
            const valueCard = document.getElementById('tile-value-card');
            if (valueCard && data.tile_ath_str) {
                valueCard.setAttribute('data-bs-title', `All-Time High: ${data.tile_ath_str}`);
                new bootstrap.Tooltip(valueCard);
            }
            
            const breakdownCard = document.getElementById('tile-breakdown-card');
            if (breakdownCard) {
                const tooltipHtml = `
                    <div class='text-start small'>
                        <div class='d-flex justify-content-between gap-3 mb-1'>
                            <span class='text-muted'>Unrealized:</span>
                            <span class='${data.tile_current_profit_raw >= 0 ? "text-success" : "text-danger"} fw-bold'>${data.tile_current_profit_str}</span>
                        </div>
                        <div class='d-flex justify-content-between gap-3 mb-1'>
                            <span class='text-muted'>Realized:</span>
                            <span class='${data.tile_realized_raw >= 0 ? "text-success" : "text-danger"} fw-bold'>${data.tile_realized_str}</span>
                        </div>
                        <div class='d-flex justify-content-between gap-3'>
                            <span class='text-muted'>Dividends:</span>
                            <span class='text-success fw-bold'>${data.tile_dividends_str}</span>
                        </div>
                    </div>
                `;
                breakdownCard.setAttribute('data-bs-title', tooltipHtml);
                new bootstrap.Tooltip(breakdownCard, { html: true });
            }
            
            const gainersCard = document.getElementById('tile-gainers-card');
            if (gainersCard && data.tile_gainers_list && data.tile_gainers_list.length > 0) {
                let title = `<div class='text-start small fw-bold mb-1 border-bottom border-light border-opacity-25 pb-1'>Top Gainers</div><ul class='text-start small mb-0 ps-3'>`;
                data.tile_gainers_list.forEach(g => {
                    title += `<li>${g.symbol}: <span class='text-success'>+${parseFloat(g.pct).toFixed(2)}%</span></li>`;
                });
                title += `</ul>`;
                gainersCard.setAttribute('data-bs-title', title);
                new bootstrap.Tooltip(gainersCard, { html: true });
            }
            
            const losersCard = document.getElementById('tile-losers-card');
            if (losersCard && data.tile_losers_list && data.tile_losers_list.length > 0) {
                let title = `<div class='text-start small fw-bold mb-1 border-bottom border-light border-opacity-25 pb-1'>Top Losers</div><ul class='text-start small mb-0 ps-3'>`;
                data.tile_losers_list.forEach(l => {
                    title += `<li>${l.symbol}: <span class='text-danger'>${parseFloat(l.pct).toFixed(2)}%</span></li>`;
                });
                title += `</ul>`;
                losersCard.setAttribute('data-bs-title', title);
                new bootstrap.Tooltip(losersCard, { html: true });
            }

            // 3. Render Transactions Table
            const tbody = document.getElementById('tx-tbody');
            if (tbody) {
                tbody.innerHTML = '';
                if (data.last_transactions && data.last_transactions.length > 0) {
                    data.last_transactions.forEach(t => {
                        const tr = document.createElement('tr');
                        tr.setAttribute('data-type', t.type);
                        
                        let badgeClass = 'bg-secondary';
                        let badgeText = t.type;
                        if (t.type === 'DEPOSIT') { badgeClass = 'bg-success bg-opacity-25 text-success border border-success border-opacity-25'; badgeText = 'DEP'; }
                        else if (t.type === 'WITHDRAWAL') { badgeClass = 'bg-secondary'; badgeText = 'WITH'; }
                        else if (t.type === 'BUY') { badgeClass = 'bg-info bg-opacity-25 text-info border border-info border-opacity-25'; badgeText = 'BUY'; }
                        else if (t.type === 'SELL') { badgeClass = 'bg-warning bg-opacity-25 text-warning border border-warning border-opacity-25'; badgeText = 'SELL'; }
                        else if (t.type === 'CLOSE') { badgeClass = 'bg-success bg-opacity-25 text-success'; badgeText = 'CLOSE'; }
                        else if (t.type === 'DIVIDEND') { badgeClass = 'bg-primary bg-opacity-25 text-primary border border-primary border-opacity-25'; badgeText = 'DIV'; }
                        else if (t.type === 'TAX') { badgeClass = 'bg-danger bg-opacity-25 text-danger'; badgeText = 'TAX'; }
                        
                        const formattedDate = new Date(t.date).toISOString().replace('T', ' ').substring(0, 19);
                        const amountClass = t.amount > 0 ? 'text-success' : 'text-danger';
                        
                        tr.innerHTML = `
                            <td class="ps-4 text-white-50">${formattedDate}</td>
                            <td><span class="badge ${badgeClass}">${badgeText}</span></td>
                            <td class="text-white small">${t.asset_display_name}</td>
                            <td class="text-end pe-4 fw-bold ${amountClass}">${t.amount.toLocaleString('pl-PL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                        `;
                        tbody.appendChild(tr);
                    });
                } else {
                    tbody.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-5">No transactions.</td></tr>`;
                }
            }

            // 4. Render Performance Card
            const perfCardBody = document.getElementById('perf-card-body');
            if (perfCardBody) {
                if (data.perf_total_closed > 0) {
                    document.getElementById('perf-content').classList.replace('d-none', 'd-flex');
                    document.getElementById('perf-empty').classList.add('d-none');
                    
                    document.getElementById('perf-win-rate').textContent = data.perf_win_rate;
                    
                    const realizedEl = document.getElementById('perf-total-realized');
                    realizedEl.textContent = data.perf_total_realized;
                    if (data.perf_total_realized_raw >= 0) {
                        realizedEl.className = 'fw-bold text-success';
                    } else {
                        realizedEl.className = 'fw-bold text-danger';
                    }
                    
                    document.getElementById('perf-wins').textContent = data.perf_win_count + 'W';
                    document.getElementById('perf-losses').textContent = data.perf_loss_count + 'L';
                    
                    if (data.perf_best_trade) {
                        document.getElementById('perf-best-row').style.display = 'flex';
                        document.getElementById('perf-best-symbol').textContent = data.perf_best_trade.symbol;
                        document.getElementById('perf-best-gain').textContent = `+${data.perf_best_trade.gain_fmt} (${data.perf_best_trade.pct_fmt}%)`;
                    } else {
                        document.getElementById('perf-best-row').style.display = 'none';
                    }
                    
                    if (data.perf_worst_trade) {
                        document.getElementById('perf-worst-row').style.display = 'flex';
                        document.getElementById('perf-worst-symbol').textContent = data.perf_worst_trade.symbol;
                        document.getElementById('perf-worst-gain').textContent = `${data.perf_worst_trade.gain_fmt} (${data.perf_worst_trade.pct_fmt}%)`;
                    } else {
                        document.getElementById('perf-worst-row').style.display = 'none';
                    }

                    // Win Rate Chart
                    const ctxWin = document.getElementById('winRateChart');
                    if (ctxWin) {
                        new Chart(ctxWin, {
                            type: 'doughnut',
                            data: {
                                labels: ['Wins', 'Losses'],
                                datasets: [{
                                    data: [data.perf_win_count, data.perf_loss_count],
                                    backgroundColor: [NEON_GREEN, SOFT_RED],
                                    borderWidth: 0,
                                    hoverOffset: 5
                                }]
                            },
                            options: {
                                maintainAspectRatio: false,
                                cutout: '80%',
                                animation: ChartDefaults.animation,
                                plugins: {
                                    legend: { display: false },
                                    tooltip: ChartDefaults.tooltip
                                }
                            }
                        });
                    }
                } else {
                    document.getElementById('perf-content').classList.add('d-none');
                    document.getElementById('perf-empty').classList.replace('d-none', 'd-block');
                }
            }

            // 5. Render ChartJS Allocation Chart
            const ctxAlloc = document.getElementById('allocationChart');
            if (ctxAlloc) {
                const allocData = {
                    'asset': {
                        labels: data.chart_labels || [],
                        values: data.chart_allocation || [],
                        colors: data.chart_colors || []
                    },
                    'sector': {
                        labels: data.chart_sector_labels || [],
                        values: data.chart_sector_values || [],
                        colors: data.chart_sector_colors || []
                    },
                    'type': {
                        labels: data.chart_type_labels || [],
                        values: data.chart_type_values || [],
                        colors: data.chart_type_colors || []
                    }
                };

                let allocChartInstance = null;

                function renderAllocChart(mode) {
                    if (allocChartInstance) allocChartInstance.destroy();
                    const d = allocData[mode];

                    if (!d || !d.values || d.values.length === 0) return;

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
                                backgroundColor: bgColors,
                                borderWidth: 0,
                                hoverOffset: 10
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            cutout: '70%',
                            animation: ChartDefaults.animation,
                            plugins: {
                                legend: {
                                    position: 'right',
                                    labels: { color: ChartDefaults.colors.text, usePointStyle: true, boxWidth: ChartDefaults.layout.boxSmall, padding: 15, font: { size: ChartDefaults.font.legendSmall } }
                                },
                                tooltip: {
                                    ...ChartDefaults.tooltip,
                                    callbacks: {
                                        label: function(context) {
                                            let label = context.label || '';
                                            let value = context.raw;
                                            return ` ${label.split(' (')[0]}: ${value.toFixed(2)} PLN`;
                                        }
                                    }
                                }
                            }
                        }
                    });
                }

                const btnGroup = document.getElementById('alloc-btn-group');
                if (btnGroup) {
                    btnGroup.querySelectorAll('.btn').forEach(btn => {
                        btn.addEventListener('click', function() {
                            btnGroup.querySelectorAll('.btn').forEach(b => b.classList.remove('active'));
                            this.classList.add('active');
                            renderAllocChart(this.getAttribute('data-mode'));
                        });
                    });
                }

                renderAllocChart('asset');
            }

            // 6. Render ChartJS Profit Chart
            const ctxProfit = document.getElementById('profitChart');
            if (ctxProfit && data.chart_profit_labels && data.chart_profit_labels.length > 0) {
                new Chart(ctxProfit, {
                    type: 'bar',
                    data: {
                        labels: data.chart_profit_labels,
                        datasets: [{
                            label: 'Gain/Loss',
                            data: data.chart_profit_values,
                            backgroundColor: data.chart_profit_values.map(v => v >= 0 ? NEON_GREEN : SOFT_RED),
                            borderRadius: 4
                        }]
                    },
                    options: {
                        maintainAspectRatio: false,
                        animation: ChartDefaults.animation,
                        scales: { x: { display: false }, y: { grid: { color: ChartDefaults.colors.grid } } },
                        plugins: { legend: { display: false }, tooltip: ChartDefaults.tooltip }
                    }
                });
            }

            // 7. Render ChartJS Timeline Chart (Main Chart)
            const ctxTimeline = document.getElementById('timelineChart');
            if (ctxTimeline && data.timeline_dates && data.timeline_dates.length > 0) {
                let mainChartInstance = null;
                const chartData = {
                    dates: data.timeline_dates,
                    value: {
                        label: 'PLN',
                        user: data.timeline_total_value,
                        inv: data.timeline_invested,
                        points: data.timeline_deposit_points,
                        wig: data.timeline_val_wig,
                        sp500: data.timeline_val_sp500,
                        acwi: data.timeline_val_acwi
                    },
                    percent: {
                        label: '%',
                        user: data.timeline_pct_user,
                        wig: data.timeline_pct_wig,
                        sp500: data.timeline_pct_sp500,
                        acwi: data.timeline_pct_acwi,
                        inf: data.timeline_pct_inflation
                    }
                };

                function renderMainChart(mode) {
                    if (mainChartInstance) mainChartInstance.destroy();
                    const ctx2d = ctxTimeline.getContext('2d');
                    const gradient = ctx2d.createLinearGradient(0, 0, 0, 400);
                    gradient.addColorStop(0, 'rgba(0, 255, 127, 0.2)');
                    gradient.addColorStop(1, 'rgba(0, 255, 127, 0.0)');

                    let datasets = [];
                    if (mode === 'value') {
                        datasets = [
                            { label: 'Portfolio', data: chartData.value.user, borderColor: MAIN_COLOR, backgroundColor: gradient, borderWidth: 2, fill: true, pointRadius: chartData.value.points, pointBackgroundColor: '#fff' },
                            { label: 'Invested', data: chartData.value.inv, borderColor: '#666', borderWidth: 2, borderDash: [4, 4], fill: false, pointRadius: 0 }
                        ];
                    } else {
                        datasets = [
                            { label: 'Portfolio %', data: chartData.percent.user, borderColor: MAIN_COLOR, backgroundColor: gradient, borderWidth: 2, fill: true, pointRadius: 0 },
                            { label: 'S&P 500 ETF (SPY)', data: chartData.percent.sp500, borderColor: '#42A5F5', borderWidth: 2, borderDash: [3, 3], fill: false, pointRadius: 0, tension: 0.1 },
                            { label: 'Global ETF (ACWI)', data: chartData.percent.acwi, borderColor: '#AB47BC', borderWidth: 2, borderDash: [3, 3], fill: false, pointRadius: 0, tension: 0.1 },
                            { label: 'Inflation', data: chartData.percent.inf, borderColor: '#ef5350', borderWidth: 2, borderDash: [2, 2], fill: false, pointRadius: 0, tension: 0.1 }
                        ];
                    }

                    mainChartInstance = new Chart(ctxTimeline, {
                        type: 'line',
                        data: { labels: chartData.dates, datasets: datasets },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            interaction: { mode: 'index', intersect: false },
                            animation: ChartDefaults.animation,
                            scales: { x: { display: false }, y: { grid: { color: ChartDefaults.colors.grid } } },
                            plugins: {
                                legend: {
                                    display: true,
                                    labels: { color: ChartDefaults.colors.text, font: { size: ChartDefaults.font.legendMain, weight: 'bold' }, boxWidth: ChartDefaults.layout.boxMain, padding: ChartDefaults.layout.padding }
                                },
                                tooltip: {
                                    ...ChartDefaults.tooltip,
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
                    const btnVal = document.getElementById('btn-val');
                    const btnPct = document.getElementById('btn-pct');
                    if (mode === 'value') {
                        if (btnVal) btnVal.classList.add('active');
                        if (btnPct) btnPct.classList.remove('active');
                        const titleEl = document.getElementById('chart-title');
                        if (titleEl) titleEl.textContent = 'Portfolio Value vs Invested Capital';
                    } else {
                        if (btnPct) btnPct.classList.add('active');
                        if (btnVal) btnVal.classList.remove('active');
                        const titleEl = document.getElementById('chart-title');
                        if (titleEl) titleEl.textContent = 'ROI vs Market Benchmarks';
                    }
                    renderMainChart(mode);
                }

                renderMainChart('value');
            }

            // 8. Hide Skeleton Loaders & Reveal Real Content (with a beautiful fade-in)
            document.querySelectorAll('.skeleton-loader').forEach(loader => {
                loader.classList.add('d-none');
            });
            document.querySelectorAll('.chart-wrapper').forEach(wrapper => {
                wrapper.classList.remove('d-none');
                wrapper.classList.add('animate-fade-in');
            });
            const perfContent = document.getElementById('perf-content');
            if (perfContent && !perfContent.classList.contains('d-none')) {
                perfContent.classList.add('animate-fade-in');
            }
            const perfEmpty = document.getElementById('perf-empty');
            if (perfEmpty && !perfEmpty.classList.contains('d-none')) {
                perfEmpty.classList.add('animate-fade-in');
            }
        })
        .catch(err => {
            console.error('Error fetching dashboard API:', err);
        });

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
    window.filterTx = filterTx;
});