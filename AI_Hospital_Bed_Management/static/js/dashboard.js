document.addEventListener("DOMContentLoaded", function () {
  const canvas = document.getElementById("occupancyChart");
  if (canvas && window.Chart) {
    const occupied = Number(canvas.dataset.occupied || 0);
    const available = Number(canvas.dataset.available || 0);
    const maintenance = Number(canvas.dataset.maintenance || 0);
    new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: ["Occupied", "Available", "Maintenance"],
        datasets: [{
          data: [occupied, available, maintenance],
          backgroundColor: ["#7866e8", "#19a982", "#e9a34b"],
          borderWidth: 0,
          hoverOffset: 5
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "76%",
        plugins: { legend: { display: false }, tooltip: { enabled: true } }
      }
    });
  }
});
