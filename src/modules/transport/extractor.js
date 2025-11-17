/**
 * Module d'extraction des données de factures de transport
 */
class TransportExtractor {
    constructor() {
        this.transportModes = ['MARITIME', 'AERIEN', 'ROUTIER', 'FERROVIAIRE'];
    }

    /**
     * Extrait les données d'une facture de transport
     * @param {string} filePath - Chemin du fichier
     * @param {string} fileData - Données du fichier en base64
     * @returns {Object} - Données extraites de la facture de transport
     */
    async extract(filePath, fileData) {
        try {
            // Pour cette version, on simule l'extraction
            return this.extractSimulated(filePath);
        } catch (error) {
            throw new Error(`Erreur lors de l'extraction de la facture de transport: ${error.message}`);
        }
    }

    /**
     * Simulation de l'extraction pour démonstration
     */
    extractSimulated(filePath) {
        return {
            numeroConnaissement: 'BL-2024-' + Math.floor(Math.random() * 10000),
            dateEmission: new Date().toISOString().split('T')[0],
            transporteur: {
                nom: 'Compagnie Maritime International',
                adresse: 'Port de Marseille, France',
                telephone: '+33 4 91 00 00 00'
            },
            modeTransport: 'MARITIME',
            portDepart: 'Marseille, France',
            portArrivee: 'Douala, Cameroun',
            dateDepart: '2024-01-15',
            dateArrivee: '2024-02-05',
            coutTransport: 3500000, // XAF
            fraisManutention: 750000,
            autresFrais: 250000,
            montantTotal: 4500000,
            devise: 'XAF',
            poids: 2500, // kg
            volume: 15, // m³
            fichierSource: filePath.split('/').pop()
        };
    }

    /**
     * Calcule le coût total du transport
     */
    calculateTotalCost(data) {
        return (data.coutTransport || 0) + 
               (data.fraisManutention || 0) + 
               (data.autresFrais || 0);
    }
}

module.exports = TransportExtractor;
