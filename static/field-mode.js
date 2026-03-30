document.addEventListener('DOMContentLoaded', () => {
    const spotsDataEl = document.getElementById('field-spots-data');
    const spots = spotsDataEl ? JSON.parse(spotsDataEl.textContent) : [];
    const statusEl = document.getElementById('status');
    const loadingEl = document.getElementById('loading');
    const spotCountEl = document.getElementById('spot-count');
    const spotCards = Array.from(document.querySelectorAll('.spot-card'));
    const sortableLists = Array.from(document.querySelectorAll('[data-sortable-spots]'));
    const directoryList = document.getElementById('spots-list');
    const geolocateBtn = document.getElementById('geolocate-btn');
    const drawer = document.getElementById('field-etiquette-drawer');
    const backdrop = document.getElementById('etiquette-backdrop');
    const trigger = document.getElementById('etiquette-trigger');
    const closeBtn = document.getElementById('etiquette-close');

    let userLat = null;
    let userLon = null;
    let map = null;
    let userLayer = null;

    if (typeof L !== 'undefined') {
        const maxCount = Math.max(...spots.map((spot) => spot.count), 1);
        const getMarkerRadius = (count) => 4 + (Math.sqrt(count / maxCount) * 8);
        const escapeHtml = (value) => String(value)
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');

        map = L.map('field-map', {
            preferCanvas: true,
            scrollWheelZoom: false,
            zoomControl: false,
        });

        L.control.zoom({ position: 'bottomright' }).addTo(map);

        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution: 'OpenStreetMap contributors, CARTO',
            maxZoom: 19,
        }).addTo(map);

        L.layerGroup(spots.map((spot) => (
            L.circleMarker([spot.lat, spot.lon], {
                radius: getMarkerRadius(spot.count),
                color: '#eadfcf',
                weight: 1.25,
                fillColor: '#79d0b4',
                fillOpacity: 0.42,
            }).bindPopup(`<strong>${escapeHtml(spot.name)}</strong><br>${spot.count} finds`)
        ))).addTo(map);

        const bounds = L.latLngBounds(spots.map((spot) => [spot.lat, spot.lon]));
        if (bounds.isValid()) {
            map.fitBounds(bounds.pad(0.08), {
                padding: [20, 20],
                maxZoom: 13,
            });
        } else {
            map.setView([41.17, -71.58], 12);
        }
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
        sortableLists.forEach((list) => {
            const sortedCards = Array.from(list.querySelectorAll('.spot-card')).sort((a, b) => {
                const distA = Number.parseFloat(a.dataset.distance || '999');
                const distB = Number.parseFloat(b.dataset.distance || '999');
                return distA - distB;
            });

            sortedCards.forEach((card) => list.appendChild(card));
        });

        if (spotCountEl && directoryList) {
            spotCountEl.textContent = `${directoryList.querySelectorAll('.spot-card').length} mapped locations (sorted by distance)`;
        }
    };

    const getUserLocation = () => {
        if (!navigator.geolocation) {
            statusEl.textContent = 'Geolocation is unavailable on this device.';
            return;
        }

        statusEl.textContent = 'Getting location...';
        loadingEl.classList.add('active');

        navigator.geolocation.getCurrentPosition(
            (position) => {
                userLat = position.coords.latitude;
                userLon = position.coords.longitude;

                statusEl.textContent = 'Location found. Shortlist and full directory sorted by distance.';

                if (map) {
                    if (userLayer) {
                        map.removeLayer(userLayer);
                    }

                    userLayer = L.layerGroup([
                        L.circle([userLat, userLon], {
                            radius: Math.max(position.coords.accuracy || 0, 25),
                            color: '#eadfcf',
                            weight: 1,
                            fillColor: '#eadfcf',
                            fillOpacity: 0.12,
                        }),
                        L.circleMarker([userLat, userLon], {
                            radius: 7,
                            color: '#0c201b',
                            weight: 2,
                            fillColor: '#eadfcf',
                            fillOpacity: 1,
                        }).bindPopup('You are here'),
                    ]).addTo(map);
                    map.flyTo([userLat, userLon], 13, { duration: 0.6 });
                }

                updateDistances();
                sortByDistance();
                loadingEl.classList.remove('active');
            },
            (error) => {
                statusEl.textContent = 'Location unavailable.';
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
