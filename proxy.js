const express = require('express');
const cors = require('cors');
const fetch = require('node-fetch');

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors({ origin: true }));
app.use(express.json());

app.use('/api', async (req, res) => {
  try {
    const { target } = req.query;
    if (!target) {
      res.status(400).json({ error: 'Missing target query parameter' });
      return;
    }

    const url = new URL(target);
    const headers = { ...req.headers };
    delete headers.host;
    delete headers.origin;
    delete headers.referer;

    const response = await fetch(url, {
      method: req.method,
      headers,
      body: ['GET', 'HEAD'].includes(req.method) ? undefined : req.body,
    });

    const data = await response.text();
    res.status(response.status);
    for (const [key, value] of response.headers.entries()) {
      if (key.toLowerCase() === 'content-length') continue;
      res.setHeader(key, value);
    }
    res.send(data);
  } catch (error) {
    console.error('Proxy error:', error);
    res.status(500).json({ error: error.message || 'Proxy error' });
  }
});

app.listen(PORT, () => {
  console.log(`Proxy server running at http://localhost:${PORT}`);
});
