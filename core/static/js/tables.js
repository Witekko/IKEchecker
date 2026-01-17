/**
 * Sorts an HTML table.
 * @param {number} n - Column index.
 * @param {string} tableId - ID of the table.
 */
function sortTable(n, tableId) {
    var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
    table = document.getElementById(tableId);
    switching = true;
    dir = "asc";

    // Reset headers
    var headers = table.getElementsByTagName("TH");
    for (i = 0; i < headers.length; i++) {
        headers[i].classList.remove("asc", "desc");
    }

    while (switching) {
        switching = false;
        rows = table.rows;
        var tbody = table.getElementsByTagName("tbody")[0];
        var bodyRows = tbody.getElementsByTagName("tr");

        for (i = 0; i < (bodyRows.length - 1); i++) {
            shouldSwitch = false;
            x = bodyRows[i].getElementsByTagName("TD")[n];
            y = bodyRows[i + 1].getElementsByTagName("TD")[n];

            var xVal = x.getAttribute("data-value") || x.innerText.toLowerCase();
            var yVal = y.getAttribute("data-value") || y.innerText.toLowerCase();

            var xNum = parseFloat(xVal);
            var yNum = parseFloat(yVal);
            var isNum = !isNaN(xNum) && !isNaN(yNum);

            if (dir == "asc") {
                if (isNum) {
                    if (xNum > yNum) { shouldSwitch = true; break; }
                } else {
                    if (xVal > yVal) { shouldSwitch = true; break; }
                }
            } else if (dir == "desc") {
                if (isNum) {
                    if (xNum < yNum) { shouldSwitch = true; break; }
                } else {
                    if (xVal < yVal) { shouldSwitch = true; break; }
                }
            }
        }
        if (shouldSwitch) {
            bodyRows[i].parentNode.insertBefore(bodyRows[i + 1], bodyRows[i]);
            switching = true;
            switchcount++;
        } else {
            if (switchcount == 0 && dir == "asc") {
                dir = "desc";
                switching = true;
            }
        }
    }
    headers[n].classList.add(dir);
}