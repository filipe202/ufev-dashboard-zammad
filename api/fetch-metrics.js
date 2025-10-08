const { handler } = require("../netlify/functions/fetch-metrics.js");

module.exports = async (req, res) => {
  try {
    const event = {
      queryStringParameters: req.query || {},
    };

    const result = await handler(event);
    const headers = result.headers || {};

    const statusCode = result.statusCode || 500;
    const body = result.body;

    Object.entries(headers).forEach(([key, value]) => {
      if (typeof value !== "undefined") {
        res.setHeader(key, value);
      }
    });

    if (headers["Content-Type"]?.includes("application/json")) {
      res.status(statusCode).send(body);
    } else {
      try {
        const parsed = typeof body === "string" ? JSON.parse(body) : body;
        res.status(statusCode).json(parsed);
      } catch (err) {
        res.status(statusCode).send(body);
      }
    }
  } catch (error) {
    console.error("/api/fetch-metrics error", error);
    res.status(500).json({ error: error.message || "Unexpected error" });
  }
};
