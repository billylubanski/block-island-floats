document.addEventListener('DOMContentLoaded', () => {
    const spotsDataEl = document.getElementById('field-spots-data');
    const spots = spotsDataEl ? JSON.parse(spotsDataEl.textContent) : [];
    const statusEl = document.getElementById('status');
    const loadingEl = document.getElementById('loading');
    const spotCountEl = document.getElementById('spot-count');
    const spotCards = Array.from(document.querySelectorAll('.spot-card'));
    const spotsList = document.getElementById('spots-list');
    const geolocateBtn = document.getElementById('geolocate-btn');
    const drawer = document.getElementById('field-etiquette-drawer');
    const backdrop = document.getElementById('etiquette-backdrop');
    const trigger = document.getElementById('etiquette-trigger');
    const closeBtn = document.getElementById('etiquette-close');

    let userLat = null;
    let userLon = null;
    let map = null;
    let userMarker = null;

    if (typeof L !== 'undefined') {
        map = L.map('field-map').setView([41.17, -71.58], 12);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '© OpenStreetMap contributors © CARTO',
            maxZoom: 19
        }).addTo(map);

        spots.forEach((spot) => {
            L.marker([spot.lat, spot.lon])
                .addTo(map)
                .bindPopup(`<b>${spot.name}</b><br>${spot.count} finds`);
        });
    }

    const setDrawerState = (isOpen) => {
        if (!drawer || !backdrop || !trigger) {
            return;
        }

        drawer.classList.toggle('is-open', isOpen);
        drawer.setAttribute('aria-hidden', String(!isOpen));
        trigger.setAttribute('aria-expanded', String(isOpen));
        backdrop.hidden = !isOpen;
        document.body.classList.toggle('field-drawer-open', isOpen);
    };

    const calculateDistance = (lat1, lon1, lat2, lon2) => {
        const earthRadiusMiles = 3959;
        const dLat = ((lat2 - lat1) * Math.PI) / 180;
        const dLon = ((lon2 - lon1) * Math.PI) / 180;
        const a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
            + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180)
            * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return earthRadiusMiles * c;
    };

    const updateDistances = () => {
        if (userLat === null || userLon === null) {
            return;
        }

        spotCards.forEach((card) => {
            const spotLat = Number.parseFloat(card.dataset.lat);
            const spotLon = Number.parseFloat(card.dataset.lon);
            const distance = calculateDistance(userLat, userLon, spotLat, spotLon);
            const distanceEl = card.querySelector('.spot-distance');

            card.dataset.distance = distance.toString();
            distanceEl.textContent = distance < 0.1
                ? `${Math.round(distance * 5280)} ft`
                : `${distance.toFixed(1)} mi`;
        });
    };

    const sortByDistance = () => {
        const sortedCards = [...spotCards].sort((a, b) => {
            const distA = Number.parseFloat(a.dataset.distance || '999');
            const distB = Number.parseFloat(b.dataset.distance || '999');
            return distA - distB;
        });

        sortedCards.forEach((card) => spotsList.appendChild(card));
        if (spotCountEl) {
            spotCountEl.textContent = `${sortedCards.length} locations (sorted by distance)`;
        }
    };

    const getUserLocation = () => {
        if (!navigator.geolocation) {
            statusEl.textContent = 'Geolocation not supported on this device.';
            return;
        }

        statusEl.textContent = 'Getting your location...';
        loadingEl.classList.add('active');

        navigator.geolocation.getCurrentPosition(
            (position) => {
                userLat = position.coords.latitude;
                userLon = position.coords.longitude;

                statusEl.textContent = `Location found. Showing ${spotCards.length} nearby spots.`;

                if (map) {
                    if (userMarker) {
                        map.removeLayer(userMarker);
                    }

                    userMarker = L.marker([userLat, userLon]).addTo(map).bindPopup('You are here').openPopup();
                    map.setView([userLat, userLon], 13);
                }

                updateDistances();
                sortByDistance();
                loadingEl.classList.remove('active');
            },
            (error) => {
                statusEl.textContent = 'Could not get location.';
                loadingEl.classList.remove('active');
                console.error('Geolocation error:', error);
            },
            {
                enableHighAccuracy: true,
                timeout: 10000
            }
        );
    };

    geolocateBtn?.addEventListener('click', getUserLocation);
    trigger?.addEventListener('click', () => setDrawerState(true));
    closeBtn?.addEventListener('click', () => setDrawerState(false));
    backdrop?.addEventListener('click', () => setDrawerState(false));

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            setDrawerState(false);
        }
    });
});
