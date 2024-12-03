async function fetchBTCData() {
    const response = await fetch('/btc_data');
    const data = await response.json();
    return data;
}

async function renderChart() {
    const btcData = await fetchBTCData();

    const ctx = document.getElementById('btcChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: btcData.timestamps,
            datasets: [{
                label: 'BTC Price (USDT)',
                data: btcData.close_prices,
                borderColor: 'rgba(75, 192, 192, 1)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                borderWidth: 1
            }]
        },
        options: {
            scales: {
                x: { title: { display: true, text: 'Time' } },
                y: { title: { display: true, text: 'Price (USDT)' } }
            }
        }
    });
}

renderChart();
