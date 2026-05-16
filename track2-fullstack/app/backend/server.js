const express = require('express');
const path = require('path');
const { initDb } = require('./db');
const animalsRouter = require('./routes/animals');
const paddocksRouter = require('./routes/paddocks');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());
app.use(express.static(path.join(__dirname, '../frontend')));

app.use('/api/animals', animalsRouter);
app.use('/api/paddocks', paddocksRouter);

initDb();

function start(port = PORT) {
  const server = app.listen(port, () => {
    const address = server.address();
    const resolvedPort = address && typeof address === 'object' ? address.port : port;
    console.log(`FarmTracker running at http://localhost:${resolvedPort}`);
  });
  return server;
}

// Global error handler — catches any uncaught synchronous throws from routes
// and ensures the response is always JSON, never an HTML error page.
app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: 'Internal server error' });
});

if (require.main === module) {
  start();
}

module.exports = app;
module.exports.start = start;
