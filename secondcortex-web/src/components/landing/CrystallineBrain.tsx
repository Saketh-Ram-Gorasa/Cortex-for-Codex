"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

export default function CrystallineBrain() {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) {
      return;
    }

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
    camera.position.z = 8;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    mount.appendChild(renderer.domElement);

    const geo = new THREE.IcosahedronGeometry(2.5, 3);
    const mat = new THREE.MeshPhysicalMaterial({
      color: "#a855f7",
      transmission: 1,
      roughness: 0.05,
      metalness: 0.2,
      emissive: new THREE.Color("#7c3aed"),
      emissiveIntensity: 0.4,
      flatShading: true,
      transparent: true,
      opacity: 1,
    });
    const brain = new THREE.Mesh(geo, mat);
    scene.add(brain);

    const count = 400;
    const particleGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);

    for (let i = 0; i < count; i += 1) {
      positions[i * 3] = (Math.random() - 0.5) * 10;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 10;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 10;
    }

    particleGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));

    const particleMat = new THREE.PointsMaterial({
      color: "#ffffff",
      size: 0.03,
      transparent: true,
      opacity: 0.9,
    });
    const particles = new THREE.Points(particleGeo, particleMat);
    scene.add(particles);

    const fallbackLogoMaterial = new THREE.SpriteMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0,
    });
    const logo = new THREE.Sprite(fallbackLogoMaterial);
    logo.scale.set(3, 3, 1);
    scene.add(logo);

    let loadedLogoTexture: THREE.Texture | null = null;
    new THREE.TextureLoader().load(
      "/logo-mark-white.png",
      (texture) => {
        loadedLogoTexture = texture;
        logo.material = new THREE.SpriteMaterial({
          map: texture,
          transparent: true,
          opacity: 0,
        });
      },
      undefined,
      () => {
        // Keep the fallback white sprite when the logo asset is not present.
      },
    );

    const light = new THREE.PointLight("#a855f7", 2);
    light.position.set(5, 5, 5);
    scene.add(light);

    const resize = () => {
      const width = mount.clientWidth;
      const height = mount.clientHeight;
      if (width === 0 || height === 0) {
        return;
      }
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    resize();
    const resizeObserver = new ResizeObserver(() => resize());
    resizeObserver.observe(mount);

    let frame = 0;
    const morphStart = 180;
    let rafId = 0;

    const animate = () => {
      rafId = window.requestAnimationFrame(animate);
      frame += 1;

      brain.rotation.y += 0.002;

      if (frame < morphStart) {
        const pos = particleGeo.attributes.position.array as Float32Array;
        for (let i = 0; i < count; i += 1) {
          const ix = i * 3;
          pos[ix] *= 0.995;
          pos[ix + 1] *= 0.995;
          pos[ix + 2] *= 0.995;
        }
        particleGeo.attributes.position.needsUpdate = true;
      }

      if (frame > morphStart) {
        const t = (frame - morphStart) / 60;
        brain.scale.setScalar(Math.max(0, 1 - t));
        mat.opacity = Math.max(0, 1 - t);

        const logoMaterial = logo.material as THREE.SpriteMaterial;
        logoMaterial.opacity = Math.min(1, t);
        logo.scale.set(3 + t, 3 + t, 1);
      }

      renderer.render(scene, camera);
    };
    animate();

    return () => {
      resizeObserver.disconnect();
      window.cancelAnimationFrame(rafId);

      geo.dispose();
      mat.dispose();
      particleGeo.dispose();
      particleMat.dispose();
      if (loadedLogoTexture) {
        loadedLogoTexture.dispose();
      }
      (logo.material as THREE.Material).dispose();
      renderer.dispose();

      if (renderer.domElement.parentElement === mount) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, []);

  return (
    <div
      ref={mountRef}
      className="hero-3d hero-brain w-full max-w-[520px] aspect-square pointer-events-none"
      style={{ filter: "drop-shadow(0 0 60px rgba(124,58,237,0.25))" }}
      aria-hidden="true"
    />
  );
}
