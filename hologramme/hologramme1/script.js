/* ==========================================================================
   COMPOSANT PUR : LOGIQUE JAVASCRIPT DE L'ORBE HOLOGRAPHIQUE
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Récupération de l'élément DOM de l'orbe
    const hologramOrb = document.getElementById('hologram-orb');
    const btnToggle = document.getElementById('btn-toggle');

    let synth = window.speechSynthesis;
    let isSpeaking = false;

    // 2. Fonction pour déclencher la résonance vocale et lumineuse
    function triggerHologramEffect() {
        if (synth && 'SpeechSynthesisUtterance' in window) {
            // Arrêter si une lecture est en cours
            synth.cancel();

            const utterance = new SpeechSynthesisUtterance(
                "Voici l'orbe holographique pur et autonome. Observez comment mon halo lumineux et mon anneau s'accélèrent lorsque je parle !"
            );
            utterance.lang = 'fr-FR';
            utterance.rate = 1.0;

            // Au début de la parole : on active la classe 'speaking'
            utterance.onstart = () => {
                isSpeaking = true;
                hologramOrb.classList.add('speaking');
                btnToggle.innerText = "⏹ Arrêter la résonance";
            };

            // À la fin ou en cas d'erreur : on retire la classe 'speaking'
            const resetOrb = () => {
                isSpeaking = false;
                hologramOrb.classList.remove('speaking');
                btnToggle.innerText = "🗣️ Tester l'effet \"Parole / Résonance\"";
            };

            utterance.onend = resetOrb;
            utterance.onerror = resetOrb;

            synth.speak(utterance);
        } else {
            // Option de repli si la synthèse vocale n'est pas dispo : bascule CSS manuelle
            isSpeaking = !isSpeaking;
            hologramOrb.classList.toggle('speaking', isSpeaking);
            btnToggle.innerText = isSpeaking ? "⏹ Arrêter la résonance" : "🗣️ Tester l'effet \"Parole / Résonance\"";
        }
    }

    // 3. Écouteurs d'événements : clic sur le bouton ou sur l'orbe lui-même !
    btnToggle.addEventListener('click', () => {
        if (isSpeaking && synth) {
            synth.cancel();
            isSpeaking = false;
            hologramOrb.classList.remove('speaking');
            btnToggle.innerText = "🗣️ Tester l'effet \"Parole / Résonance\"";
        } else {
            triggerHologramEffect();
        }
    });

    hologramOrb.addEventListener('click', triggerHologramEffect);
});
