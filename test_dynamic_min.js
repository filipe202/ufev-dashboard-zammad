// Teste do cálculo dinâmico do limite mínimo de tickets

function testDynamicMinTickets() {
  const testCases = [
    { totalTickets: 50, expected: Math.max(5, Math.min(50, Math.ceil(50 * 0.1))) }, // 5
    { totalTickets: 100, expected: Math.max(5, Math.min(50, Math.ceil(100 * 0.1))) }, // 10
    { totalTickets: 200, expected: Math.max(5, Math.min(50, Math.ceil(200 * 0.1))) }, // 20
    { totalTickets: 500, expected: Math.max(5, Math.min(50, Math.ceil(500 * 0.1))) }, // 50
    { totalTickets: 1000, expected: Math.max(5, Math.min(50, Math.ceil(1000 * 0.1))) }, // 50 (máximo)
    { totalTickets: 30, expected: Math.max(5, Math.min(50, Math.ceil(30 * 0.1))) }, // 5 (mínimo)
  ];

  console.log("Teste do cálculo dinâmico do limite mínimo:");
  console.log("Total Tickets | Limite Dinâmico | Percentual");
  console.log("-------------|----------------|----------");
  
  testCases.forEach(({ totalTickets, expected }) => {
    const percentage = ((expected / totalTickets) * 100).toFixed(1);
    console.log(`${totalTickets.toString().padStart(12)} | ${expected.toString().padStart(14)} | ${percentage.padStart(8)}%`);
  });
}

testDynamicMinTickets();
