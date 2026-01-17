document.addEventListener('DOMContentLoaded', function() {
    function getData(id) {
        try { return JSON.parse(document.getElementById(id).textContent); }
        catch (e) { return []; }
    }

    const SOFT_BLUE = '#42a5f5';
    const NEON_GREEN = '#00ff7f';

    // 1. ROCZNY WYKRES (Bar)
    const ctxYear = document.getElementById('yearlyChart');
    if (ctxYear) {
        new Chart(ctxYear, {
            type: 'bar',
            data: {
                labels: getData('d-years-lbl'),
                datasets: [{
                    label: 'Net Dividends',
                    data: getData('d-years-val'),
                    backgroundColor: NEON_GREEN,
                    borderRadius: 4,
                    barPercentage: 0.5
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#888' } },
                    y: { grid: { color: '#333', borderDash: [4, 4] }, ticks: { color: '#888' } }
                },
                plugins: { legend: { display: false } }
            }
        });
    }

    // 2. MIESIĘCZNY WYKRES (Line)
    const ctxMonth = document.getElementById('monthlyChart');
    if (ctxMonth) {
        const monthLabels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        let monthlyChart = new Chart(ctxMonth, {
            type: 'line',
            data: {
                labels: monthLabels,
                datasets: [{
                    label: 'Monthly',
                    data: getData('d-months-val'), // Domyślnie ostatni rok
                    borderColor: SOFT_BLUE,
                    backgroundColor: 'rgba(66, 165, 245, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointBackgroundColor: SOFT_BLUE
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { display: false }, ticks: { color: '#888' } },
                    y: { grid: { display: false } }
                },
                plugins: { legend: { display: false } }
            }
        });

        // Obsługa zmiany roku
        const yearSelector = document.getElementById('yearSelector');
        if (yearSelector) {
            const allData = getData('d-all-months'); // Słownik {2024: [...], 2025: [...]}

            yearSelector.addEventListener('change', function() {
                const selectedYear = this.value;
                if (allData[selectedYear]) {
                    monthlyChart.data.datasets[0].data = allData[selectedYear];
                    monthlyChart.update();
                }
            });
        }
    }
});