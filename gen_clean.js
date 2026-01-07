const fs = require('fs');
const { execSync } = require('child_process');

const payPeriods = [
  { payDate: '09/15/2025', periodStart: '09/01/2025', periodEnd: '09/15/2025', rateType: 'old' },
  { payDate: '09/30/2025', periodStart: '09/16/2025', periodEnd: '09/30/2025', rateType: 'old' },
  { payDate: '10/15/2025', periodStart: '10/01/2025', periodEnd: '10/15/2025', rateType: 'old' },
  { payDate: '10/31/2025', periodStart: '10/16/2025', periodEnd: '10/31/2025', rateType: 'old' },
  { payDate: '11/14/2025', periodStart: '11/01/2025', periodEnd: '11/15/2025', rateType: 'new' },
  { payDate: '11/28/2025', periodStart: '11/16/2025', periodEnd: '11/30/2025', rateType: 'new' },
  { payDate: '12/15/2025', periodStart: '12/01/2025', periodEnd: '12/15/2025', rateType: 'new' },
  { payDate: '12/31/2025', periodStart: '12/16/2025', periodEnd: '12/31/2025', rateType: 'new' },
];

const baseline = {
  gross: 97174.28, federal: 9632.11, ss: 5592.44, medicare: 1307.90, vaState: 4220.47,
  medical: 6356.93, dental: 523.71, vision: 92.82, k401: 8875.79, transam: 171.40,
};

const oldRates = {
  gross: 8416.67, federal: 834.09, ss: 485.36, medicare: 113.51, vaState: 363.36,
  medical: 536.26, dental: 44.18, vision: 7.83, k401: 841.67, transam: 17.14, net: 5173.27,
};

const newRates = {
  gross: 8416.67, federal: 826.64, ss: 483.26, medicare: 113.02, vaState: 361.41,
  medical: 583.22, dental: 31.09, vision: 7.83, k401: 841.67, transam: 0.00, net: 5168.53,
};

const fmt = (n) => n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const fmtC = (n) => '$' + fmt(n);

function generateHTML(period, rates, ytds) {
  const taxC = rates.federal + rates.ss + rates.medicare + rates.vaState;
  const taxY = ytds.federal + ytds.ss + ytds.medicare + ytds.vaState;
  const dedC = rates.medical + rates.dental + rates.vision + rates.k401 + rates.transam;
  const dedY = ytds.medical + ytds.dental + ytds.vision + ytds.k401 + ytds.transam;

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@page {
  size: 8.5in 11in;
  margin: 0;
}
html, body {
  margin: 0;
  padding: 0;
  width: 8.5in;
  height: 11in;
}
body {
  font-family: Helvetica, Arial, sans-serif;
  font-size: 10pt;
  position: relative;
}

/* Blue bars - full bleed */
.bar-top {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 0.07in;
  background: #1a0980;
}
.bar-mid {
  position: absolute;
  top: 3.35in;
  left: 0;
  right: 0;
  height: 0.06in;
  background: #1a0980;
}

/* Top section */
.company {
  position: absolute;
  top: 0.65in;
  left: 1.09in;
  line-height: 11.7pt;
  font-size: 10pt;
  font-family: Helvetica, Arial, sans-serif;
}

.paystub-info {
  position: absolute;
  top: 1.55in;
  right: 1.2in;
  text-align: right;
  line-height: 11.7pt;
  font-size: 10pt;
  font-family: Helvetica, Arial, sans-serif;
}

.employee-top {
  position: absolute;
  top: 2.20in;
  left: 1.11in;
  line-height: 11.7pt;
  font-size: 10pt;
  font-family: Helvetica, Arial, sans-serif;
}

/* Middle section - after bar */
.employer-section {
  position: absolute;
  top: 3.78in;
  left: 0.54in;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
}
.section-label {
  font-weight: bold;
  margin-bottom: 0;
  line-height: 10.45pt;
}
.section-content {
  line-height: 10.1pt;
}

.payperiod-section {
  position: absolute;
  top: 3.97in;
  left: 4.42in;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
}
.payperiod-label {
  font-weight: bold;
  line-height: 9.4pt;
  margin-bottom: 0;
}
.payperiod-table {
  border-collapse: collapse;
}
.payperiod-table td {
  padding: 0;
  font-size: 9pt;
  line-height: 9.1pt;
  vertical-align: top;
}
.payperiod-table td:first-child {
  padding-right: 0.3in;
}
.payperiod-table td:last-child {
  text-align: right;
  width: 1in;
}

.employee-section {
  position: absolute;
  top: 4.97in;
  left: 0.54in;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
}

.netpay-mid {
  position: absolute;
  top: 6.12in;
  left: 4.41in;
  right: 0.54in;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
}
.netpay-mid-label { font-weight: bold; }
.netpay-mid-value {
  float: right;
  font-weight: bold;
}

/* Data tables */
.memo {
  position: absolute;
  top: 6.67in;
  left: 0.54in;
  font-weight: bold;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
}

.pay-section {
  position: absolute;
  top: 7.37in;
  left: 0.53in;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
}

.ded-section {
  position: absolute;
  top: 7.37in;
  left: 4.50in;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
}

.tax-section {
  position: absolute;
  top: 9.26in;
  left: 0.53in;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
}

.summary-section {
  position: absolute;
  top: 9.35in;
  left: 4.50in;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
}

.netpay-final {
  position: absolute;
  top: 10.22in;
  left: 4.39in;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
}
.netpay-final-label { font-weight: bold; font-size: 11pt; }
.netpay-final-value { font-weight: bold; font-size: 12pt; margin-left: 0.3in; }

/* Table styling */
table {
  border-collapse: collapse;
  font-size: 9pt;
  font-family: Helvetica, Arial, sans-serif;
  line-height: 9pt;
  table-layout: fixed;
}
th {
  font-weight: bold;
  text-align: left;
  padding: 0 0.08in 0.03in 0;
  white-space: nowrap;
  line-height: 9pt;
  border-bottom: 1pt solid #000;
}
th.r { text-align: right; }
td {
  padding: 0.02in 0.08in 0.02in 0;
  white-space: nowrap;
  line-height: 9pt;
}
td.r { text-align: right; }

/* Left side tables - PAY and TAXES aligned */
.pay-section table,
.tax-section table {
  width: 3.50in;
}
.pay-section .col-label { width: 1.00in; }
.pay-section .col-hours { width: 0.60in; }
.pay-section .col-rate { width: 0.50in; }
.pay-section .col-current { width: 0.65in; }
.pay-section .col-ytd { width: 0.75in; }

.tax-section .col-label { width: 2.10in; }
.tax-section .col-current { width: 0.65in; }
.tax-section .col-ytd { width: 0.75in; }

/* Right side tables - DEDUCTIONS and SUMMARY */
.ded-section table {
  width: 3.20in;
}
.ded-section .col-label { width: 1.80in; }
.ded-section .col-current { width: 0.65in; }
.ded-section .col-ytd { width: 0.75in; }

.summary-section table {
  border: 1pt solid #000;
  width: 3.35in;
}
.summary-section .col-label { width: 1.80in; }
.summary-section .col-current { width: 0.65in; }
.summary-section .col-ytd { width: 0.90in; }
.summary-section th {
  border-bottom: 1pt solid #000;
  padding: 0.03in 0.1in;
}
.summary-section td {
  border: none;
  padding: 0.03in 0.1in;
}
</style>
</head>
<body>
  <div class="bar-top"></div>

  <div class="company">Cognitio Corp<br>1750 Tysons Blvd<br>Ste 1500<br>McLean VA 22102</div>

  <div class="paystub-info">Pay Stub Detail<br>PAY DATE: ${period.payDate}<br>NET PAY: ${fmtC(rates.net)}</div>

  <div class="employee-top">Todd Forstell<br>585 Parishville Rd<br>Gore VA 22637</div>

  <div class="bar-mid"></div>

  <div class="employer-section">
    <div class="section-label">EMPLOYER</div>
    <div class="section-content">Cognitio Corp<br>1750 Tysons Blvd<br>Ste 1500<br>McLean VA 22102</div>
  </div>

  <div class="payperiod-section">
    <div class="payperiod-label">PAY PERIOD</div>
    <table class="payperiod-table">
      <tr><td>Period Beginning</td><td>${period.periodStart}</td></tr>
      <tr><td>Period Ending:</td><td>${period.periodEnd}</td></tr>
      <tr><td>Pay Date:</td><td>${period.payDate}</td></tr>
    </table>
  </div>

  <div class="employee-section">
    <div class="section-label">EMPLOYEE</div>
    <div class="section-content">Todd Forstell<br>585 Parishville Rd<br>Gore VA 22637</div>
  </div>

  <div class="netpay-mid">
    <span class="netpay-mid-label">NET PAY:</span>
    <span class="netpay-mid-value">${fmtC(rates.net)}</span>
  </div>

  <div class="memo">MEMO:</div>

  <div class="pay-section">
    <table>
      <colgroup>
        <col class="col-label">
        <col class="col-hours">
        <col class="col-rate">
        <col class="col-current">
        <col class="col-ytd">
      </colgroup>
      <tr><th>PAY</th><th class="r">Hours</th><th class="r">Rate</th><th class="r">Current</th><th class="r">YTD</th></tr>
      <tr><td>Salary</td><td class="r">-</td><td class="r">-</td><td class="r">${fmt(rates.gross)}</td><td class="r">${fmt(ytds.gross)}</td></tr>
    </table>
  </div>

  <div class="ded-section">
    <table>
      <colgroup>
        <col class="col-label">
        <col class="col-current">
        <col class="col-ytd">
      </colgroup>
      <tr><th>DEDUCTIONS</th><th class="r">Current</th><th class="r">YTD</th></tr>
      <tr><td>Anthem Medical</td><td class="r">${fmt(rates.medical)}</td><td class="r">${fmt(ytds.medical)}</td></tr>
      <tr><td>Anthem Dental</td><td class="r">${fmt(rates.dental)}</td><td class="r">${fmt(ytds.dental)}</td></tr>
      <tr><td>VSP Vision</td><td class="r">${fmt(rates.vision)}</td><td class="r">${fmt(ytds.vision)}</td></tr>
      <tr><td>CUNA 401k</td><td class="r">${fmt(rates.k401)}</td><td class="r">${fmt(ytds.k401)}</td></tr>
      <tr><td>TransAmerica Accident</td><td class="r">${fmt(rates.transam)}</td><td class="r">${fmt(ytds.transam)}</td></tr>
    </table>
  </div>

  <div class="tax-section">
    <table>
      <colgroup>
        <col class="col-label">
        <col class="col-current">
        <col class="col-ytd">
      </colgroup>
      <tr><th>TAXES</th><th class="r">Current</th><th class="r">YTD</th></tr>
      <tr><td>Federal Income Tax</td><td class="r">${fmt(rates.federal)}</td><td class="r">${fmt(ytds.federal)}</td></tr>
      <tr><td>Social Security</td><td class="r">${fmt(rates.ss)}</td><td class="r">${fmt(ytds.ss)}</td></tr>
      <tr><td>Medicare</td><td class="r">${fmt(rates.medicare)}</td><td class="r">${fmt(ytds.medicare)}</td></tr>
      <tr><td>VA Income Tax</td><td class="r">${fmt(rates.vaState)}</td><td class="r">${fmt(ytds.vaState)}</td></tr>
    </table>
  </div>

  <div class="summary-section">
    <table>
      <colgroup>
        <col class="col-label">
        <col class="col-current">
        <col class="col-ytd">
      </colgroup>
      <tr><th>SUMMARY</th><th class="r">Current</th><th class="r">YTD</th></tr>
      <tr><td>Total Pay</td><td class="r">${fmtC(rates.gross)}</td><td class="r">${fmtC(ytds.gross)}</td></tr>
      <tr><td>Taxes</td><td class="r">${fmtC(taxC)}</td><td class="r">${fmtC(taxY)}</td></tr>
      <tr><td>Deductions</td><td class="r">${fmtC(dedC)}</td><td class="r">${fmtC(dedY)}</td></tr>
    </table>
  </div>

  <div class="netpay-final">
    <span class="netpay-final-label">Net Pay</span>
    <span class="netpay-final-value">${fmtC(rates.net)}</span>
  </div>
</body>
</html>`;
}

function main() {
  const outputDir = '/home/user/lindernote.github.io/paystubs_output';
  fs.rmSync(outputDir, { recursive: true, force: true });
  fs.mkdirSync(outputDir, { recursive: true });

  const ytds = { ...baseline };

  for (const period of payPeriods) {
    const rates = period.rateType === 'old' ? oldRates : newRates;
    Object.keys(ytds).forEach(k => { ytds[k] += rates[k] || 0; });

    const html = generateHTML(period, rates, { ...ytds });
    const dateParts = period.payDate.split('/');
    const baseName = `25${dateParts[0]}${dateParts[1]}_PayRecords_TForstell`;

    fs.writeFileSync(`${outputDir}/${baseName}.html`, html);

    try {
      execSync(`weasyprint "${outputDir}/${baseName}.html" "${outputDir}/${baseName}.pdf" 2>/dev/null`);
      console.log(`${baseName}.pdf`);
    } catch (e) {
      console.log(`${baseName}.html (PDF failed)`);
    }
  }
}

main();
