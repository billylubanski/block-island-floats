document.addEventListener('DOMContentLoaded', () => {
    const spotsDataEl = document.getElementById('field-spots-data');
    const spots = spotsDataEl ? JSON.parse(spotsDataEl.textContent) : [];
    const statusEl = document.getElementById('status');
    const loadingEl = document.getElementById('loading');
    const spotCountEl = document.getElementById('spot-count');
    const spotCards = Array.from(document.querySelectorAll('.spot-card'));
    const sortableLists = Array.from(document.querySelectorAll('[data-sortable-spots]'));
    const directoryList = document.getElementById('spots-list');
    const directoryProgressEl = document.getElementById('field-directory-progress');
    const directoryRevealBtn = document.getElementById('field-directory-reveal');
    const geolocateBtn = document.getElementById('geolocate-btn');
    const statusDetailEl = document.getElementById('status-detail');
    const statusHelpEl = document.getElementById('status-help');
    const drawer = document.getElementById('field-etiquette-drawer');
    const backdrop = document.getElementById('etiquette-backdrop');
    const trigger = document.getElementById('etiquette-trigger');
    const closeBtn = document.getElementById('etiquette-close');
    const appleMapsLinks = Array.from(document.querySelectorAll('[data-apple-maps-link]'));

    let userLat = null;
    let userLon = null;
    let map = null;
    let userLayer = null;
    let lastFocusedDrawerElement = null;
    const directoryBatchSize = Number.parseInt(directoryRevealBtn?.dataset.batchSize || '0', 10)
        || (directoryList ? directoryList.querySelectorAll('.spot-card').length : 0);
    const defaultLocationLabel = 'Find my location';
    const loadingLocationLabel = 'Getting location...';
    const retryLocationLabel = 'Try again';
    const refreshLocationLabel = 'Refresh location';
    const fallbackMessage = 'You can still use the shortlist and map manually.';

    const permissionHelpText = () => {
        const userAgent = navigator.userAgent || '';

        if (/iPhone|iPad|iPod/i.test(userAgent)) {
            return 'Open Safari website settings, set Location to Allow, then try again.';
        }
        if (/Macintosh/i.test(userAgent) && /Safari/i.test(userAgent) && !/Chrome|Chromium|Edg/i.test(userAgent)) {
            return 'Open Safari Settings for This Website, allow location access, then try again.';
        }
        if (/Chrome|Chromium|Edg/i.test(userAgent)) {
            return 'Use the site settings icon in the address bar, allow location access, then try again.';
        }

        return 'Check your browser or device location permissions, allow access for this site, then try again.';
    };

    const supportsAppleMaps = () => {
        const platform = navigator.userAgentData?.platform || navigator.platform || '';
        const userAgent = navigator.userAgent || '';
        return /Mac|iPhone|iPad|iPod/i.test(`${platform} ${userAgent}`);
    };

    const getFocusableElements = (container) => {
        if (!container) {
            return [];
        }

        return Array.from(
            container.querySelectorAll(
                'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )
        ).filter((element) => !element.hidden && element.getAttribute('aria-hidden') !== 'true');
    };

    const setButtonState = ({ disabled = false, label = defaultLocationLabel }) => {
        if (!geolocateBtn) {
            return;
        }

        geolocateBtn.disabled = disabled;
        geolocateBtn.textContent = label;
    };

    const setLocationStatus = ({
        summary,
        detail = '',
        help = '',
        state = 'idle',
    }) => {
        if (statusEl) {
            statusEl.textContent = summary;
            statusEl.dataset.state = state;
        }
        if (statusDetailEl) {
            statusDetailEl.textContent = detail;
        }
        if (statusHelpEl) {
            statusHelpEl.textContent = help;
            statusHelpEl.hidden = !help;
        }
    };

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

        if (isOpen) {
            lastFocusedDrawerElement = document.activeElement instanceof HTMLElement
                ? document.activeElement
                : trigger;
        }

        drawer.classList.toggle('is-open', isOpen);
        drawer.setAttribute('aria-hidden', String(!isOpen));
        trigger.setAttribute('aria-expanded', String(isOpen));
        backdrop.hidden = !isOpen;
        document.body.classList.toggle('field-drawer-open', isOpen);

        if (isOpen) {
            closeBtn?.focus();
        } else if (lastFocusedDrawerElement instanceof HTMLElement) {
            lastFocusedDrawerElement.focus();
        } else {
            trigger.focus();
        }
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

    const updateDirectoryRevealState = () => {
        const cardsInOrder = directoryList ? Array.from(directoryList.querySelectorAll('.spot-card')) : [];
        if (!cardsInOrder.length) {
            return;
        }

        const hiddenCards = cardsInOrder.filter((card) => card.hidden);
        const shownCount = cardsInOrder.length - hiddenCards.length;

        if (directoryProgressEl) {
            directoryProgressEl.textContent = hiddenCards.length
                ? `Showing ${shownCount} of ${cardsInOrder.length} mapped locations.`
                : `Showing all ${cardsInOrder.length} mapped locations.`;
        }

        if (!directoryRevealBtn) {
            return;
        }

        if (!hiddenCards.length) {
            directoryRevealBtn.hidden = true;
            return;
        }

        const revealCount = Math.min(directoryBatchSize, hiddenCards.length);
        directoryRevealBtn.textContent = `Show ${revealCount} more locations`;
        directoryRevealBtn.hidden = false;
    };

    const getUserLocation = () => {
        if (!navigator.geolocation) {
            setButtonState({ label: retryLocationLabel });
            setLocationStatus({
                summary: 'This browser does not support geolocation.',
                detail: fallbackMessage,
                help: 'Open this page in a browser with location support, or keep using the shortlist and map manually.',
                state: 'error',
            });
            return;
        }

        setButtonState({ disabled: true, label: loadingLocationLabel });
        setLocationStatus({
            summary: 'Getting location...',
            detail: 'Allow location access when your browser asks so the shortlist can be sorted by distance.',
            state: 'loading',
        });
        loadingEl.classList.add('active');

        navigator.geolocation.getCurrentPosition(
            (position) => {
                userLat = position.coords.latitude;
                userLon = position.coords.longitude;

                setButtonState({ label: refreshLocationLabel });
                setLocationStatus({
                    summary: 'Location found. Shortlist and full directory sorted by distance.',
                    detail: 'Use Refresh location if you move to a new trailhead or parking area.',
                    state: 'success',
                });

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
                document.body.classList.add('field-distance-ready');
                sortByDistance();
                updateDirectoryRevealState();
                loadingEl.classList.remove('active');
            },
            (error) => {
                let summary = 'Location request failed.';
                let detail = fallbackMessage;
                let help = 'Check your location settings and try again.';

                if (error && error.code === 1) {
                    summary = 'Location access was blocked.';
                    detail = fallbackMessage;
                    help = permissionHelpText();
                } else if (error && error.code === 2) {
                    summary = 'Location could not be determined.';
                    detail = 'Your device could not return a reliable position. Move to a clearer area or wait for a stronger signal.';
                    help = 'Keep using the shortlist and map manually, then try again when the device has a better fix.';
                } else if (error && error.code === 3) {
                    summary = 'Location request timed out.';
                    detail = 'The device did not return a position before the request expired.';
                    help = 'Try again from the same spot, or keep using the shortlist and map manually.';
                }

                setButtonState({ label: retryLocationLabel });
                setLocationStatus({
                    summary,
                    detail,
                    help,
                    state: 'error',
                });
                loadingEl.classList.remove('active');
                console.warn('Geolocation unavailable:', error);
            },
            {
                enableHighAccuracy: true,
                timeout: 10000
            }
        );
    };

    geolocateBtn?.addEventListener('click', getUserLocation);
    directoryRevealBtn?.addEventListener('click', () => {
        const hiddenCards = directoryList
            ? Array.from(directoryList.querySelectorAll('.spot-card')).filter((card) => card.hidden)
            : [];
        hiddenCards.slice(0, directoryBatchSize).forEach((card) => {
            card.hidden = false;
        });
        updateDirectoryRevealState();
    });
    trigger?.addEventListener('click', () => setDrawerState(true));
    closeBtn?.addEventListener('click', () => setDrawerState(false));
    backdrop?.addEventListener('click', () => setDrawerState(false));

    document.addEventListener('keydown', (event) => {
        if (drawer?.classList.contains('is-open') && event.key === 'Tab') {
            const focusable = getFocusableElements(drawer);
            if (focusable.length) {
                const first = focusable[0];
                const last = focusable[focusable.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                    event.preventDefault();
                    last.focus();
                    return;
                }
                if (!event.shiftKey && document.activeElement === last) {
                    event.preventDefault();
                    first.focus();
                    return;
                }
            }
        }

        if (event.key === 'Escape') {
            setDrawerState(false);
        }
    });

    if (supportsAppleMaps()) {
        appleMapsLinks.forEach((link) => {
            link.hidden = false;
        });
    }

    updateDirectoryRevealState();
});
