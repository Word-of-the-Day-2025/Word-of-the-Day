/* Open the side navigation */
function openNav() {
    document.getElementById("mobile-menu").style.display = "block";
    document.getElementById("mobile-menu").style.width = "75%";
    document.getElementById("overlay").style.display = "block";
}

/* Set the width of the side navigation to 0 */
function closeNav() {
    document.getElementById("mobile-menu").style.display = "none";
    document.getElementById("mobile-menu").style.width = "0";
    document.getElementById("overlay").style.display = "none";
}