document.addEventListener('DOMContentLoaded', () => {
    const mapEl = document.getElementById('map');
    const dataEl = document.getElementById('dashboard-map-data');
    const loadingEl = document.getElementById('map-loading');
    const geolocateBtn = document.getElementById('dashboard-geolocate');
    const toggleButtons = Array.from(document.querySelectorAll('[data-layer-toggle]'));
    const focusListEl = document.getElementById('map-focus-list');
    const focusHeadingEl = document.getElementById('map-focus-heading');
    const focusSubtitleEl = document.getElementById('map-focus-subtitle');
    const focusNoteEl = document.getElementById('map-focus-note');
    const resetViewBtn = document.getElementById('map-reset-view');

    if (!mapEl || !dataEl) {
        return;
    }

    let mapData = null;

    try {
        mapData = JSON.parse(dataEl.textContent);
    } catch (error) {
        console.error('Unable to parse dashboard map data.', error);
        if (loadingEl) {
            loadingEl.style.display = 'none';
        }
        return;
    }

    const clusters = Array.isArray(mapData?.clusters) ? mapData.clusters : [];
    const maxCount = Math.max(Number(mapData?.max_count || 0), 1);
    const defaultCenter = Array.isArray(mapData?.center) ? mapData.center : [41.17, -71.58];

    if (!clusters.length || typeof L === 'undefined') {
        if (loadingEl) {
            loadingEl.style.display = 'none';
        }
        return;
    }

    let map = null;
    let heatLayer = null;
    let spotLayer = null;
    let userLayer = null;
    let markers = [];
    let overviewBounds = null;
    let activeClusterIndex = 0;
    let hasInitialized = false;

    const escapeHtml = (value) => String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');

    const calculateDistanceMiles = (lat1, lon1, lat2, lon2) => {
        const earthRadiusMiles = 3959;
        const dLat = ((lat2 - lat1) * Math.PI) / 180;
        const dLon = ((lon2 - lon1) * Math.PI) / 180;
        const a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
            + Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180)
            * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return earthRadiusMiles * c;
    };

    const formatDistance = (miles) => (
        miles < 0.1
            ? `${Math.round(miles * 5280)} ft away`
            : `${miles.toFixed(1)} mi away`
    );

    const hideLoading = () => {
        if (loadingEl) {
            loadingEl.style.display = 'none';
        }
    };

    const buildFocusCardMarkup = (cluster, index, options = {}) => {
        const label = options.distance !== undefined
            ? formatDistance(options.distance)
            : (index === 0 ? 'Top cluster' : `Hotspot ${index + 1}`);

        const metaParts = [`${cluster.count} finds`, `${cluster.spot_count} spot${cluster.spot_count === 1 ? '' : 's'}`];
        if (options.distance !== undefined) {
            metaParts.unshift(formatDistance(options.distance));
        }

        return `
            <button class="map-focus-card${index === 0 && options.makeFirstActive !== false ? ' is-active' : ''}" type="button" data-cluster-index="${options.clusterIndex}">
                <span class="map-focus-card__eyebrow">${label}</span>
                <span class="map-focus-card__title">${escapeHtml(cluster.label)}</span>
                <span class="map-focus-card__meta">${metaParts.join(' | ')}</span>
            </button>
        `;
    };

    const syncActiveFocusCard = () => {
        if (!focusListEl) {
            return;
        }

        const cards = Array.from(focusListEl.querySelectorAll('[data-cluster-index]'));
        cards.forEach((card) => {
            card.classList.toggle('is-active', Number(card.dataset.clusterIndex) === activeClusterIndex);
        });
    };

    const bindFocusCards = () => {
        if (!focusListEl) {
            return;
        }

        focusListEl.querySelectorAll('[data-cluster-index]').forEach((button) => {
            button.addEventListener('click', () => {
                focusCluster(Number(button.dataset.clusterIndex));
            });
        });

        syncActiveFocusCard();
    };

    const renderFocusCards = (items, config = {}) => {
        if (focusHeadingEl && config.heading) {
            focusHeadingEl.textContent = config.heading;
        }

        if (focusSubtitleEl && config.subtitle) {
            focusSubtitleEl.textContent = config.subtitle;
        }

        if (focusNoteEl && config.note) {
            focusNoteEl.textContent = config.note;
        }

        if (!focusListEl) {
            return;
        }

        focusListEl.innerHTML = items.map((item, index) => buildFocusCardMarkup(item.cluster, index, item)).join('');
        bindFocusCards();
    };

    const setToggleState = (layerName, isActive) => {
        const button = toggleButtons.find((item) => item.dataset.layerToggle === layerName);
        if (!button) {
            return;
        }

        button.classList.toggle('is-active', isActive);
        button.setAttribute('aria-pressed', String(isActive));
    };

    const setLayerVisible = (layerName, isVisible) => {
        const layer = layerName === 'heat' ? heatLayer : spotLayer;
        setToggleState(layerName, isVisible);

        if (!map || !layer) {
            return;
        }

        if (isVisible && !map.hasLayer(layer)) {
            layer.addTo(map);
        }

        if (!isVisible && map.hasLayer(layer)) {
            map.removeLayer(layer);
        }
    };

    const buildPopupHtml = (cluster) => {
        const spotItems = cluster.spots.map((spot) => (
            `<li><span>${escapeHtml(spot.name)}</span><strong>${spot.count}</strong></li>`
        )).join('');

        const extraSpots = cluster.remaining_spot_count > 0
            ? `<p class="map-popup__extra">+${cluster.remaining_spot_count} more nearby spot${cluster.remaining_spot_count === 1 ? '' : 's'}</p>`
            : '';

        return `
            <div class="map-popup">
                <strong>${escapeHtml(cluster.label)}</strong>
                <p>${cluster.count} reported finds across ${cluster.spot_count} named spot${cluster.spot_count === 1 ? '' : 's'}.</p>
                <ul class="map-popup__list">${spotItems}</ul>
                ${extraSpots}
            </div>
        `;
    };

    const getHeatWeight = (count) => {
        const normalized = Math.sqrt(count / maxCount);
        return Math.max(normalized, 0.18);
    };

    const getMarkerRadius = (count) => {
        const normalized = Math.sqrt(count / maxCount);
        return 6 + (normalized * 12);
    };

    const getMarkerStyle = (cluster, isActive = false) => ({
        radius: getMarkerRadius(cluster.count) + (isActive ? 2 : 0),
        color: isActive ? '#f4efe7' : '#eadfcf',
        weight: isActive ? 2.4 : 1.5,
        fillColor: isActive ? '#b5f0d8' : '#79d0b4',
        fillOpacity: isActive ? 0.82 : 0.48,
    });

    const setActiveCluster = (index = null) => {
        activeClusterIndex = Number.isInteger(index) ? index : null;

        markers.forEach((marker, markerIndex) => {
            const cluster = clusters[markerIndex];
            marker.setStyle(getMarkerStyle(cluster, markerIndex === activeClusterIndex));
        });

        syncActiveFocusCard();
    };

    const focusCluster = (index) => {
        ensureMap();

        if (!Number.isInteger(index) || !clusters[index] || !markers[index]) {
            return;
        }

        if (!spotLayer || !map.hasLayer(spotLayer)) {
            setLayerVisible('spots', true);
        }

        const cluster = clusters[index];
        setActiveCluster(index);
        map.flyTo([cluster.lat, cluster.lon], 15, {
            duration: 0.55,
        });
        markers[index].openPopup();
    };

    const resetMapView = () => {
        ensureMap();
        setActiveCluster(null);
        map.closePopup();

        if (overviewBounds?.isValid()) {
            map.fitBounds(overviewBounds.pad(0.08), {
                padding: [24, 24],
                maxZoom: 14,
            });
            return;
        }

        map.setView(defaultCenter, 13);
    };

    const initMap = () => {
        if (hasInitialized) {
            return;
        }

        hasInitialized = true;

        map = L.map(mapEl, {
            preferCanvas: true,
            scrollWheelZoom: false,
            zoomControl: false,
        });

        L.control.zoom({ position: 'bottomright' }).addTo(map);

        const tileLayer = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19,
        });

        tileLayer.on('load', hideLoading);
        tileLayer.on('tileerror', hideLoading);
        tileLayer.addTo(map);

        if (typeof L.heatLayer === 'function') {
            heatLayer = L.heatLayer(
                clusters.map((cluster) => [cluster.lat, cluster.lon, getHeatWeight(cluster.count)]),
                {
                    radius: 30,
                    blur: 24,
                    maxZoom: 14,
                    max: 1,
                    gradient: {
                        0.0: '#4f8f90',
                        0.45: '#79d0b4',
                        1.0: '#2b6077',
                    },
                },
            );
            heatLayer.addTo(map);
        } else {
            setToggleState('heat', false);
            const heatToggle = toggleButtons.find((button) => button.dataset.layerToggle === 'heat');
            if (heatToggle) {
                heatToggle.disabled = true;
            }
        }

        markers = clusters.map((cluster, index) => {
            const marker = L.circleMarker([cluster.lat, cluster.lon], getMarkerStyle(cluster, index === activeClusterIndex))
                .bindPopup(buildPopupHtml(cluster));

            marker.on('click', () => {
                setActiveCluster(index);
            });

            return marker;
        });

        spotLayer = L.layerGroup(markers);
        spotLayer.addTo(map);

        overviewBounds = L.latLngBounds(clusters.map((cluster) => [cluster.lat, cluster.lon]));
        if (overviewBounds.isValid()) {
            map.fitBounds(overviewBounds.pad(0.08), {
                padding: [24, 24],
                maxZoom: 14,
            });
        } else {
            map.setView(defaultCenter, 13);
        }

        map.whenReady(() => {
            hideLoading();
            window.setTimeout(() => map.invalidateSize(), 0);
        });

        window.setTimeout(hideLoading, 3500);
    };

    const ensureMap = () => {
        initMap();
        if (map) {
            map.invalidateSize();
        }
    };

    renderFocusCards(
        clusters.slice(0, 5).map((cluster, index) => ({
            cluster,
            clusterIndex: index,
        })),
        {
            heading: 'Top mapped clusters',
            subtitle: 'Use the scouting rail to jump the map to the strongest historical areas.',
            note: 'The rail starts with historical density and rewrites itself by proximity once you geolocate.',
        },
    );

    // Keep the map off the critical path until the viewport is close enough to use it.
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            if (!entries.some((entry) => entry.isIntersecting)) {
                return;
            }

            observer.disconnect();
            ensureMap();
        }, {
            rootMargin: '240px 0px',
        });

        observer.observe(mapEl);
    } else {
        ensureMap();
    }

    toggleButtons.forEach((button) => {
        button.addEventListener('click', () => {
            ensureMap();
            const layerName = button.dataset.layerToggle;
            const nextState = button.getAttribute('aria-pressed') !== 'true';
            setLayerVisible(layerName, nextState);
        });
    });

    resetViewBtn?.addEventListener('click', resetMapView);

    geolocateBtn?.addEventListener('click', () => {
        ensureMap();

        if (!navigator.geolocation) {
            alert('Geolocation is not supported by your browser.');
            return;
        }

        const originalLabel = geolocateBtn.textContent;
        geolocateBtn.disabled = true;
        geolocateBtn.textContent = 'Locating...';

        navigator.geolocation.getCurrentPosition((position) => {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;
            const accuracy = Math.max(position.coords.accuracy || 0, 25);

            if (userLayer) {
                map.removeLayer(userLayer);
            }

            userLayer = L.layerGroup([
                L.circle([lat, lon], {
                    radius: accuracy,
                    color: '#eadfcf',
                    weight: 1,
                    fillColor: '#eadfcf',
                    fillOpacity: 0.12,
                }),
                L.circleMarker([lat, lon], {
                    radius: 7,
                    color: '#0c201b',
                    weight: 2,
                    fillColor: '#eadfcf',
                    fillOpacity: 1,
                }).bindPopup('You are here'),
            ]).addTo(map);

            map.flyTo([lat, lon], 14, {
                duration: 0.6,
            });

            const nearestClusters = clusters
                .map((cluster, index) => ({
                    cluster,
                    clusterIndex: index,
                    distance: calculateDistanceMiles(lat, lon, cluster.lat, cluster.lon),
                    makeFirstActive: false,
                }))
                .sort((left, right) => left.distance - right.distance)
                .slice(0, 5);

            setActiveCluster(null);
            renderFocusCards(nearestClusters, {
                heading: 'Closest mapped clusters',
                subtitle: 'Re-ranked from your pin so you can scout outward with less backtracking.',
                note: nearestClusters.length
                    ? `Nearest cluster: ${nearestClusters[0].cluster.label}, ${formatDistance(nearestClusters[0].distance)}.`
                    : 'No mapped clusters available.',
            });

            geolocateBtn.disabled = false;
            geolocateBtn.textContent = originalLabel;
        }, () => {
            geolocateBtn.disabled = false;
            geolocateBtn.textContent = originalLabel;
            alert('Unable to retrieve your location.');
        }, {
            enableHighAccuracy: true,
            timeout: 10000,
        });
    });
});
