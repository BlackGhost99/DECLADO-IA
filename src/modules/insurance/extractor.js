/**
 * Module d'extraction des données de factures d'assurance
 */
class InsuranceExtractor {
    constructor() {
        this.insuranceTypes = ['MARITIME', 'AERIENNE', 'TERRESTRE', 'TOUS_RISQUES'];
    }

    /**
     * Extrait les données d'une facture d'assurance
     * @param {string} filePath - Chemin du fichier
     * @param {string} fileData - Données du fichier en base64
     * @returns {Object} - Données extraites de la facture d'assurance
     */
    async extract(filePath, fileData) {
        try {
            // Pour cette version, on simule l'extraction
            return this.extractSimulated(filePath);
        } catch (error) {
            throw new Error(`Erreur lors de l'extraction de la facture d'assurance: ${error.message}`);
        }
    }

    /**
     * Simulation de l'extraction pour démonstration
     */
    extractSimulated(filePath) {
        return {
            numeroPolice: 'POL-2024-' + Math.floor(Math.random() * 10000),
            dateEmission: new Date().toISOString().split('T')[0],
            assureur: {
                nom: 'Compagnie d\'Assurance International',
                adresse: '456 Avenue de l\'Assurance, Paris, France',
                telephone: '+33 1 45 67 89 01'
            },
            typeAssurance: 'TOUS_RISQUES',
            valeurAssuree: 56000000, // XAF
            tauxPrime: 0.5, // 0.5%
            primeAssurance: 280000, // XAF
            franchise: 100000,
            dateDebut: '2024-01-15',
            dateFin: '2024-02-15',
            couverture: 'Tous risques transport maritime',
            devise: 'XAF',
            fichierSource: filePath.split('/').pop()
        };
    }

    /**
     * Calcule le montant de la prime d'assurance
     */
    calculatePremium(valeurAssuree, tauxPrime) {
        return valeurAssuree * (tauxPrime / 100);
    }
}

module.exports = InsuranceExtractor;
