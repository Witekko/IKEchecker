document.addEventListener('DOMContentLoaded', function() {
    // 1. LOADER LOGIC
    const loader = document.getElementById('page-loader');

    // Pokaż loader przy kliknięciu w linki (chyba że to kotwica lub JS)
    document.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            const target = this.getAttribute('target');
            if (href && href !== '#' && !href.startsWith('#') && !href.includes('javascript') && target !== '_blank' && !href.includes('logout')) {
                loader.style.display = 'flex';
            }
        });
    });

    // Pokaż loader przy wysyłaniu formularzy
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', () => loader.style.display = 'flex');
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
});

// Ukryj loader po powrocie (cache przeglądarki)
window.addEventListener('pageshow', (e) => {
    if(e.persisted) document.getElementById('page-loader').style.display = 'none';
});