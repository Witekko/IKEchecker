document.addEventListener('DOMContentLoaded', function() {
    // --- PORTFOLIO SETTINGS: ADD TRANSACTION MODAL ---
    const typeSelect = document.getElementById('txType');

    if (typeSelect) {
        const assetFields = document.getElementById('assetFields');
        const qtyInput = document.getElementById('txQty');
        const priceInput = document.getElementById('txPrice');
        const amountInput = document.getElementById('txAmount');
        const calcInfo = document.getElementById('calcInfo');

        function updateFields() {
            const type = typeSelect.value;
            // Dla typów pieniężnych (bez akcji) ukrywamy pola symbolu i ceny
            if (['DEPOSIT', 'WITHDRAWAL', 'TAX'].includes(type)) {
                if(assetFields) assetFields.style.display = 'none';
                if(calcInfo) calcInfo.style.display = 'none';
                if(amountInput) amountInput.readOnly = false; // Pozwól wpisać kwotę
            } else {
                if(assetFields) assetFields.style.display = 'block';
                if(calcInfo) calcInfo.style.display = 'block';
                // Przy BUY/SELL kwota może być liczona automatycznie
            }
        }

        function calculateTotal() {
            const qty = parseFloat(qtyInput.value) || 0;
            const price = parseFloat(priceInput.value) || 0;

            if (qty > 0 && price > 0) {
                const total = (qty * price).toFixed(2);
                amountInput.value = total;
            }
        }

        typeSelect.addEventListener('change', updateFields);
        if(qtyInput) qtyInput.addEventListener('input', calculateTotal);
        if(priceInput) priceInput.addEventListener('input', calculateTotal);

        // Init
        updateFields();
    }
});