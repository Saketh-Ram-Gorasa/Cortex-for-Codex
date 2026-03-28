"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

type NeuralNode = {
  mesh: THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>;
  pulseSpeed: number;
  pulseOffset: number;
};

export default function BrainScene() {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) {
      return;
    }

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    mount.appendChild(renderer.domElement);

    const sphereRoot = new THREE.Group();
    scene.add(sphereRoot);

    const nodeCount = 120;
    const nodeRadius = 2.5;
    const nodeGeometry = new THREE.SphereGeometry(0.04, 10, 10);
    const nodeMaterial = new THREE.MeshBasicMaterial({ color: 0x06b6d4 });
    const nodes: NeuralNode[] = [];
    const edges: THREE.Line[] = [];
    const phi = Math.PI * (3 - Math.sqrt(5));

    for (let i = 0; i < nodeCount; i += 1) {
      const y = 1 - (i / (nodeCount - 1)) * 2;
      const radius = Math.sqrt(1 - y * y);
      const theta = phi * i;

      const mesh = new THREE.Mesh(nodeGeometry, nodeMaterial.clone());
      mesh.position.set(
        Math.cos(theta) * radius * nodeRadius,
        y * nodeRadius,
        Math.sin(theta) * radius * nodeRadius,
      );

      nodes.push({
        mesh,
        pulseSpeed: 0.02 + Math.random() * 0.03,
        pulseOffset: Math.random() * Math.PI * 2,
      });
      sphereRoot.add(mesh);
    }

    const edgeMaterial = new THREE.LineBasicMaterial({
      color: 0x8b5cf6,
      transparent: true,
      opacity: 0.3,
    });

    for (let i = 0; i < nodeCount; i += 1) {
      for (let j = i + 1; j < nodeCount; j += 1) {
        const distance = nodes[i].mesh.position.distanceTo(nodes[j].mesh.position);
        if (distance < 1.8) {
          const geometry = new THREE.BufferGeometry().setFromPoints([
            nodes[i].mesh.position,
            nodes[j].mesh.position,
          ]);
          const edge = new THREE.Line(geometry, edgeMaterial);
          edges.push(edge);
          sphereRoot.add(edge);
        }
      }
    }

    const shellGeometry = new THREE.SphereGeometry(2.62, 32, 32);
    const shellWireframe = new THREE.WireframeGeometry(shellGeometry);
    const shellMaterial = new THREE.LineBasicMaterial({
      color: 0x4a9eed,
      transparent: true,
      opacity: 0.08,
    });
    const shell = new THREE.LineSegments(shellWireframe, shellMaterial);
    sphereRoot.add(shell);

    camera.position.z = 6;

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

    let animationFrameId = 0;
    let frame = 0;

    const animate = () => {
      animationFrameId = window.requestAnimationFrame(animate);
      frame += 1;

      sphereRoot.rotation.y += 0.003;
      sphereRoot.rotation.x += 0.001;

      nodes.forEach((node) => {
        const pulse = Math.sin(frame * node.pulseSpeed + node.pulseOffset);
        const scale = 1 + 0.4 * pulse;
        node.mesh.scale.setScalar(scale);
        const t = (pulse + 1) / 2;
        node.mesh.material.color.setHex(t > 0.5 ? 0x06b6d4 : 0x8b5cf6);
      });

      renderer.render(scene, camera);
    };
    animate();

    const handleMouseMove = (event: MouseEvent) => {
      const rect = mount.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;
      sphereRoot.rotation.y += x * 0.01;
      sphereRoot.rotation.x += y * 0.01;
    };

    window.addEventListener("mousemove", handleMouseMove);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      resizeObserver.disconnect();
      window.cancelAnimationFrame(animationFrameId);

      nodes.forEach((node) => node.mesh.material.dispose());
      nodeMaterial.dispose();
      nodeGeometry.dispose();
      edgeMaterial.dispose();
      edges.forEach((edge) => edge.geometry.dispose());
      shellMaterial.dispose();
      shellWireframe.dispose();
      shellGeometry.dispose();

      renderer.dispose();
      if (renderer.domElement.parentElement === mount) {
        mount.removeChild(renderer.domElement);
      }
    };
  }, []);

  return (
    <div
      ref={mountRef}
      className="hero-3d pointer-events-none w-full max-w-[520px] aspect-square opacity-0 hero-brain"
      style={{
        filter: "drop-shadow(0 0 40px rgba(6,182,212,0.30))",
        background:
          "radial-gradient(ellipse at 60% 50%, rgba(139,92,246,0.16) 0%, rgba(6,182,212,0.08) 42%, rgba(8,16,42,0) 74%)",
      }}
      aria-hidden="true"
    />
  );
}

