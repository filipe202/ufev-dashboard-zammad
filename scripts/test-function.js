const { handler } = require("../netlify/functions/fetch-metrics.js");

const event = {
  queryStringParameters: {
    from: "2025-09-30", // ou deixe vazio
  },
};

handler(event).then((resp) => {
  console.log("status:", resp.statusCode);
  console.log(resp.body);
}).catch((err) => {
  console.error("Function error:", err);
});