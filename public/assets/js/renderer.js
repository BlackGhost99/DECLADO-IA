const { ipcRenderer } = require('electron');
const InvoiceExtractor = require('../../src/modules/invoice/extractor');
const TransportExtractor = require('../../src/modules/transport/extractor');
const InsuranceExtractor = require('../../src/modules/insurance/extractor');
const TaxCalculator = require('../../src/modules/tax-calculator/calculator');
const DeclarationGenerator = require('../../src/utils/declarationGenerator');

// État de l'application
const appState = {
    invoiceData: null,
    transportData: null,
    insuranceData: null,
    calculatedTaxes: null,
    declaration: null
};

// Initialisation des modules
const invoiceExtractor = new InvoiceExtractor();
const transportExtractor = new TransportExtractor();
const insuranceExtractor = new InsuranceExtractor();
const taxCalculator = new TaxCalculator();
const declarationGenerator = new DeclarationGenerator();

// Gestionnaires d'événements
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    loadSampleData();
});

function setupEventListeners() {
    document.getElementById('btn-upload-invoice').addEventListener('click', () => uploadDocument('invoice'));
    document.getElementById('btn-upload-transport').addEventListener('click', () => uploadDocument('transport'));
    document.getElementById('btn-upload-insurance').addEventListener('click', () => uploadDocument('insurance'));
    document.getElementById('btn-calculate').addEventListener('click', calculateTaxes);
    document.getElementById('btn-generate').addEventListener('click', generateDeclaration);
    document.getElementById('btn-export').addEventListener('click', exportDeclaration);
    document.getElementById('btn-reset').addEventListener('click', resetApplication);
}

async function uploadDocument(type) {
    try {
        const filePath = await ipcRenderer.invoke('select-invoice-file');
        if (!filePath) return;

        const statusElement = document.getElementById(`${type}-status`);
        statusElement.textContent = '⏳ Traitement en cours...';
        statusElement.className = 'status loading';

        // Lire le fichier
        const fileData = await ipcRenderer.invoke('read-file', filePath);
        
        if (!fileData.success) {
            throw new Error(fileData.error);
        }

        // Extraire les données selon le type
        let extractedData;
        switch(type) {
            case 'invoice':
                extractedData = await invoiceExtractor.extract(filePath, fileData.data);
                appState.invoiceData = extractedData;
                break;
            case 'transport':
                extractedData = await transportExtractor.extract(filePath, fileData.data);
                appState.transportData = extractedData;
                break;
            case 'insurance':
                extractedData = await insuranceExtractor.extract(filePath, fileData.data);
                appState.insuranceData = extractedData;
                break;
        }

        statusElement.textContent = `✅ Chargé: ${filePath.split('/').pop()}`;
        statusElement.className = 'status success';

        updateExtractedDataDisplay();
        enableCalculateButton();

    } catch (error) {
        const statusElement = document.getElementById(`${type}-status`);
        statusElement.textContent = `❌ Erreur: ${error.message}`;
        statusElement.className = 'status error';
    }
}

function updateExtractedDataDisplay() {
    const container = document.getElementById('extracted-data');
    
    if (!appState.invoiceData && !appState.transportData && !appState.insuranceData) {
        container.innerHTML = '<div class="data-preview"><p class="placeholder">Les données apparaîtront ici après le chargement des documents...</p></div>';
        return;
    }

    let html = '<div class="data-preview">';
    
    if (appState.invoiceData) {
        html += '<h3>📄 Facture Commerciale</h3>';
        html += '<table class="data-table">';
        html += '<tr><th>Champ</th><th>Valeur</th></tr>';
        for (const [key, value] of Object.entries(appState.invoiceData)) {
            html += `<tr><td>${key}</td><td>${value}</td></tr>`;
        }
        html += '</table>';
    }

    if (appState.transportData) {
        html += '<h3 style="margin-top: 20px;">🚚 Facture de Transport</h3>';
        html += '<table class="data-table">';
        html += '<tr><th>Champ</th><th>Valeur</th></tr>';
        for (const [key, value] of Object.entries(appState.transportData)) {
            html += `<tr><td>${key}</td><td>${value}</td></tr>`;
        }
        html += '</table>';
    }

    if (appState.insuranceData) {
        html += '<h3 style="margin-top: 20px;">🛡️ Facture d\'Assurance</h3>';
        html += '<table class="data-table">';
        html += '<tr><th>Champ</th><th>Valeur</th></tr>';
        for (const [key, value] of Object.entries(appState.insuranceData)) {
            html += `<tr><td>${key}</td><td>${value}</td></tr>`;
        }
        html += '</table>';
    }

    html += '</div>';
    container.innerHTML = html;
}

function enableCalculateButton() {
    const hasInvoice = appState.invoiceData !== null;
    document.getElementById('btn-calculate').disabled = !hasInvoice;
}

function calculateTaxes() {
    if (!appState.invoiceData) {
        alert('Veuillez charger au moins une facture commerciale');
        return;
    }

    try {
        // Calculer les taxes
        appState.calculatedTaxes = taxCalculator.calculate(
            appState.invoiceData,
            appState.transportData,
            appState.insuranceData
        );

        // Mettre à jour l'affichage
        updateTaxDisplay(appState.calculatedTaxes);

        // Activer les boutons de génération et export
        document.getElementById('btn-generate').disabled = false;
        document.getElementById('btn-export').disabled = false;

    } catch (error) {
        alert(`Erreur lors du calcul des taxes: ${error.message}`);
    }
}

function updateTaxDisplay(taxes) {
    document.getElementById('cif-value').textContent = formatCurrency(taxes.cifValue);
    document.getElementById('customs-duty').textContent = formatCurrency(taxes.customsDuty);
    document.getElementById('vat').textContent = formatCurrency(taxes.vat);
    document.getElementById('tci').textContent = formatCurrency(taxes.tci);
    document.getElementById('statistical-fee').textContent = formatCurrency(taxes.statisticalFee);
    document.getElementById('total-amount').textContent = formatCurrency(taxes.total);
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('fr-FR', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount) + ' XAF';
}

function generateDeclaration() {
    if (!appState.calculatedTaxes) {
        alert('Veuillez d\'abord calculer les taxes');
        return;
    }

    try {
        appState.declaration = declarationGenerator.generate(
            appState.invoiceData,
            appState.transportData,
            appState.insuranceData,
            appState.calculatedTaxes
        );

        // Afficher l'aperçu
        const previewSection = document.getElementById('declaration-preview');
        const contentDiv = document.getElementById('declaration-content');
        
        contentDiv.textContent = JSON.stringify(appState.declaration, null, 2);
        previewSection.style.display = 'block';

        // Faire défiler vers l'aperçu
        previewSection.scrollIntoView({ behavior: 'smooth' });

    } catch (error) {
        alert(`Erreur lors de la génération de la déclaration: ${error.message}`);
    }
}

async function exportDeclaration() {
    if (!appState.declaration) {
        alert('Veuillez d\'abord générer la déclaration');
        return;
    }

    try {
        const result = await ipcRenderer.invoke('save-declaration', appState.declaration);
        
        if (result.success) {
            alert(`✅ Déclaration exportée avec succès:\n${result.path}`);
        } else {
            alert(`❌ Erreur lors de l'export: ${result.error}`);
        }
    } catch (error) {
        alert(`❌ Erreur: ${error.message}`);
    }
}

function resetApplication() {
    if (!confirm('Voulez-vous vraiment réinitialiser l\'application? Toutes les données seront perdues.')) {
        return;
    }

    // Réinitialiser l'état
    appState.invoiceData = null;
    appState.transportData = null;
    appState.insuranceData = null;
    appState.calculatedTaxes = null;
    appState.declaration = null;

    // Réinitialiser l'interface
    document.getElementById('invoice-status').textContent = '';
    document.getElementById('transport-status').textContent = '';
    document.getElementById('insurance-status').textContent = '';
    
    updateExtractedDataDisplay();
    
    document.getElementById('cif-value').textContent = '0.00 XAF';
    document.getElementById('customs-duty').textContent = '0.00 XAF';
    document.getElementById('vat').textContent = '0.00 XAF';
    document.getElementById('tci').textContent = '0.00 XAF';
    document.getElementById('statistical-fee').textContent = '0.00 XAF';
    document.getElementById('total-amount').textContent = '0.00 XAF';

    document.getElementById('declaration-preview').style.display = 'none';

    document.getElementById('btn-calculate').disabled = true;
    document.getElementById('btn-generate').disabled = true;
    document.getElementById('btn-export').disabled = true;
}

function loadSampleData() {
    // Cette fonction peut charger des données d'exemple pour faciliter les tests
    console.log('Application prête - Mode hors-ligne activé');
}
